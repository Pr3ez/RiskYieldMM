"""Generate the declarative Raw-V8 Step-2 maximum-protocol V2 seed catalog.

This program constructs design authority only.  It is not either of the two
independent F1 counters and it does not read a witness, pilot, maximum row, or
producer output.  The emitted catalog closes the recurrence kernels, resource
metrics, 475-case universe, and the analytic LOCAL_SHUTDOWN case-475 proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
CATALOG_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_v2_seed_catalog.v1"
)
CATALOG_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolV2SeedCatalogV1V4_9F_RawV8"
)
PROTOCOL_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.constructive_maximum_protocol.v2"
)
IDENTITY_ENVELOPE_VERSION: Final = (
    "riskyieldmm.semantic_identity.compact_canonical_json_sha256.v1"
)

INVENTORY_PATH: Final = Path("tests/raw_v8_step2_inventory_v4_v49f.json")
INVENTORY_OCTETS: Final = 5_265_855
INVENTORY_RAW_SHA256: Final = (
    "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
)
INVENTORY_ID: Final = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
STRUCTURAL_REGISTRY_PATH: Final = Path(
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
STRUCTURAL_REGISTRY_OCTETS: Final = 1_469_663
STRUCTURAL_REGISTRY_RAW_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
STRUCTURAL_REGISTRY_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
RULE_LITERAL_PATH: Final = Path(
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
RULE_LITERAL_OCTETS: Final = 484_301
RULE_LITERAL_RAW_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
COMPACT_CORRECTION_PATH: Final = Path(
    "docs/research/"
    "v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md"
)
COMPACT_CORRECTION_OCTETS: Final = 49_849
COMPACT_CORRECTION_RAW_SHA256: Final = (
    "f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4"
)
NORMATIVE_DOCUMENT_SOURCES: Final = (
    (
        "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
        Path(
            "docs/research/"
            "v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md"
        ),
        212_471,
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388",
    ),
    (
        "STEP2_V2_CONTRACT_FREEZE",
        Path("docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md"),
        34_591,
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c",
    ),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        Path(
            "docs/research/"
            "v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md"
        ),
        217_135,
        "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55",
    ),
    (
        "STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION",
        COMPACT_CORRECTION_PATH,
        COMPACT_CORRECTION_OCTETS,
        COMPACT_CORRECTION_RAW_SHA256,
    ),
    (
        "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
        Path(
            "docs/research/"
            "v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md"
        ),
        435_478,
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a",
    ),
)
OUTPUT_PATH: Final = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)

MAXIMUM_ROW_UNIVERSE_SHA256: Final = (
    "836db59c1111080882dea078a27847b130d18eed474a8982ebad2e062d532d1c"
)
LOCAL_PROFILE_ID: Final = (
    "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
)
BASELINE_OPERATION_SPEC_ID: Final = (
    "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
)
BASELINE_RESULT_ID: Final = (
    "237336c1d3867c7b38d3dcf4d9af455f4dc4675ae2dd1af6ba89b04d010be5db"
)
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
UINT128_MAXIMUM: Final = (1 << 128) - 1
CELL_TRANSFER_RULE_CATALOG_PATH: Final = Path(
    "scripts/tests/raw_v8_step2_cell_transfer_rule_catalog_v49f.json"
)
CELL_TRANSFER_RULE_CATALOG_OCTETS: Final = 108_000
CELL_TRANSFER_RULE_CATALOG_RAW_SHA256: Final = (
    "0d6efae04daa148d755ce49fe84b70d188cfd736257b3bb0714fb25876c357f2"
)
CASE_EVENT_GRAMMAR_PATH: Final = Path(
    "scripts/tests/raw_v8_step2_case_event_grammar_v49f.json"
)
CASE_EVENT_GRAMMAR_OCTETS: Final = 131_015
CASE_EVENT_GRAMMAR_RAW_SHA256: Final = (
    "72bfd44ff159eb6904936ae32d0d25ab9b0c8536b87f5e93d055b521679401c8"
)
CASE_EVENT_HAND_ORACLES_PATH: Final = Path(
    "scripts/tests/raw_v8_step2_case_event_hand_oracles_v49f.json"
)
CASE_EVENT_HAND_ORACLES_OCTETS: Final = 310_490
CASE_EVENT_HAND_ORACLES_RAW_SHA256: Final = (
    "4e234065d43a02f69e6a4c6cdf89bff3656c07a6f66c909ddbba9c55ead703a4"
)

_TRANSFER_OPCODE_CONTRACTS: Final = {
    "CELL_FIXED_OCTETS_V1": {
        "semantic_rule": "FIXED_EXACT_OR_EMPTY_V1",
        "ordered_required_parameter_names": ["fixed_canonical_octets"],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_BOOLEAN_LITERAL_V1": {
        "semantic_rule": "BOOLEAN_LITERAL_OR_FULL_DOMAIN_SENTINEL_V1",
        "ordered_required_parameter_names": ["boolean_literal"],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_SAFE_INTEGER_INTERVAL_V1": {
        "semantic_rule": "SIGNED_SAFE_INTEGER_ENDPOINT_AND_NEAREST_ZERO_V1",
        "ordered_required_parameter_names": [
            "integer_minimum",
            "integer_maximum",
            "ordered_probe_values",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_FINITE_TEXT_V1": {
        "semantic_rule": "FINITE_CANONICAL_STRING_LENGTH_EXTREMA_V1",
        "ordered_required_parameter_names": [
            "text_language_position",
            "text_language_id",
            "ordered_literals",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_BOUNDED_TEXT_OCTETS_V1": {
        "semantic_rule": "BOUNDED_CANONICAL_STRING_OCTET_INTERVAL_V1",
        "ordered_required_parameter_names": [
            "built_in_language_kind",
            "minimum_canonical_octets",
            "maximum_canonical_octets",
            "text_language_id",
            "text_language_position",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_RELAXED_JSON_STRING_V1": {
        "semantic_rule": "ALL_CANONICAL_JSON_STRINGS_UNDER_EFFECTIVE_CEILING_V1",
        "ordered_required_parameter_names": [
            "text_language_position",
            "text_language_id",
            "language_kind",
            "built_in_language_kind",
            "ascii_dfa_id",
            "unicode_identifier_profile_id",
            "minimum_utf8_octets",
            "maximum_utf8_octets",
            "minimum_decoded_octets",
            "maximum_decoded_octets",
            "decimal_maximum",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_DERIVED_IDENTITY_V1": {
        "semantic_rule": "FIXED_EXACT_OR_EMPTY_V1",
        "ordered_required_parameter_names": ["canonical_octets"],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_NULLABLE_V1": {
        "semantic_rule": "NULL_LITERAL_AND_NON_NULL_CHILD_UNION_V1",
        "ordered_required_parameter_names": ["child_step_position"],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_CHILD_BOUNDS_ALIAS_V1": {
        "semantic_rule": "VALIDATED_CHILD_BOUNDS_ALIAS_V1",
        "ordered_required_parameter_names": [
            "referenced_type_name",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_ARRAY_BATCH_V1": {
        "semantic_rule": "HOMOGENEOUS_ARRAY_CLOSED_INTERVAL_V1",
        "ordered_required_parameter_names": [
            "minimum_items",
            "maximum_items",
            "item_value_schema_id",
            "item_step_position",
            "ordered_run_records",
            "observer_closure_record",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "BATCH_ITEM_SUMMARY_V1",
    },
    "CELL_ARRAY_STREAM_V1": {
        "semantic_rule": "HOMOGENEOUS_ARRAY_CLOSED_INTERVAL_V1",
        "ordered_required_parameter_names": [
            "minimum_items",
            "maximum_items",
            "item_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "STREAM_ITEM_SUMMARY_V1",
    },
    "CELL_RECORD_V1": {
        "semantic_rule": "RECORD_SYNTAX_PLUS_ORDERED_CHILD_SUM_V1",
        "ordered_required_parameter_names": [
            "record_member_count",
            "ordered_member_records",
            "record_syntax_octets_excluding_child_values",
        ],
        "child_read_mode": "ORDERED_MEMBER_EARLIER_POSITIONS_V1",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_UNION_V1": {
        "semantic_rule": "ORDERED_NONEMPTY_ALTERNATIVE_INTERVAL_UNION_V1",
        "ordered_required_parameter_names": [
            "ordered_alternative_records",
            "owner_type_name",
            "owner_typed_member_path",
        ],
        "child_read_mode": "ORDERED_ALTERNATIVE_EARLIER_POSITIONS_V1",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_CODEC_INTERSECTION_V1": {
        "semantic_rule": "RECOMPUTED_CODEC_RESIDUAL_INTERSECTION_V1",
        "ordered_required_parameter_names": [
            "ordered_codec_coordinate_records",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_SAFE_RELAXATION_V1": {
        "semantic_rule": "VALIDATED_BOUND_PRESERVING_ALIAS_V1",
        "ordered_required_parameter_names": [
            "safe_relaxation_rule_id",
            "authority_predicate_locator",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_SCOPE_ROOT_V1": {
        "semantic_rule": "VALIDATED_BOUND_PRESERVING_ALIAS_V1",
        "ordered_required_parameter_names": [
            "case_binding",
            "fixed_authority_bindings",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_APPLICATION_WRAPPER_V1": {
        "semantic_rule": "VALIDATED_BOUND_PRESERVING_ALIAS_V1",
        "ordered_required_parameter_names": [
            "ordered_application_invocation_records",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_LOCAL_SHUTDOWN_SWEEP_V2": {
        "semantic_rule": "EXACT_CHAINED_LOCAL_CONTROLLER_TERMINAL_WINNER_V2",
        "ordered_required_parameter_names": ["local_shutdown_analytic_catalog_id"],
        "child_read_mode": "RESOLVE_BOUND_LOCAL_CATALOG_V1",
        "state_rule": "LOCAL_TERMINAL_EIGHT_COMPONENT_STATE_V1",
    },
}

_TRANSFER_RULE_NAME_BY_OPCODE: Final = {
    "CELL_FIXED_OCTETS_V1": "FIXED_EXACT_OR_EMPTY_V1",
    "CELL_BOOLEAN_LITERAL_V1": "BOOLEAN_LITERAL_OR_FULL_DOMAIN_SENTINEL_V1",
    "CELL_SAFE_INTEGER_INTERVAL_V1": "SIGNED_SAFE_INTEGER_ENDPOINT_AND_NEAREST_ZERO_V1",
    "CELL_FINITE_TEXT_V1": "FINITE_CANONICAL_STRING_LENGTH_EXTREMA_V1",
    "CELL_BOUNDED_TEXT_OCTETS_V1": "BOUNDED_CANONICAL_STRING_OCTET_INTERVAL_V1",
    "CELL_RELAXED_JSON_STRING_V1": "ALL_CANONICAL_JSON_STRINGS_UNDER_EFFECTIVE_CEILING_V1",
    "CELL_DERIVED_IDENTITY_V1": "DERIVED_IDENTITY_EXACT_OR_EMPTY_V1",
    "CELL_NULLABLE_V1": "NULL_LITERAL_AND_NON_NULL_CHILD_UNION_V1",
    "CELL_CHILD_BOUNDS_ALIAS_V1": "VALIDATED_CHILD_BOUNDS_ALIAS_V1",
    "CELL_ARRAY_BATCH_V1": "HOMOGENEOUS_ARRAY_BATCH_INTERVAL_V1",
    "CELL_ARRAY_STREAM_V1": "HOMOGENEOUS_ARRAY_STREAM_INTERVAL_V1",
    "CELL_RECORD_V1": "RECORD_SYNTAX_PLUS_ORDERED_CHILD_SUM_V1",
    "CELL_UNION_V1": "ORDERED_NONEMPTY_ALTERNATIVE_INTERVAL_UNION_V1",
    "CELL_CODEC_INTERSECTION_V1": "RECOMPUTED_CODEC_RESIDUAL_INTERSECTION_V1",
    "CELL_SAFE_RELAXATION_V1": "VALIDATED_RELAXATION_ALIAS_V1",
    "CELL_SCOPE_ROOT_V1": "VALIDATED_SCOPE_ALIAS_V1",
    "CELL_APPLICATION_WRAPPER_V1": "VALIDATED_APPLICATION_ALIAS_V1",
    "CELL_LOCAL_SHUTDOWN_SWEEP_V2": "EXACT_CHAINED_LOCAL_CONTROLLER_TERMINAL_WINNER_V2",
}

UNICODE_SOURCES: Final = (
    (
        "DerivedNormalizationProps.txt",
        837_688,
        "d5687a48c95c7d6e1ec59cb29c0f2e8b052018eb069a4371b7368d0561e12a29",
    ),
    (
        "NormalizationTest.txt",
        2_625_136,
        "fb9ac8cc154a80cad6caac9897af55a4e75176af6f4e2bb6edc2bf8b1d57f326",
    ),
    (
        "PropList.txt",
        132_360,
        "e05c0a2811d113dae4abd832884199a3ea8d187ee1b872d8240a788a96540bfd",
    ),
    (
        "CompositionExclusions.txt",
        8_911,
        "3b019c0a33c3140cbc920c078f4f9af2680ba4f71869c8d4de5190667c70b6a3",
    ),
    (
        "ReadMe.txt",
        635,
        "53672c0d0b5185e3cf04c8e970d544c3af81ae7c8eeba0b9cf6d355aa954ae1f",
    ),
    (
        "UnicodeData.txt",
        1_913_704,
        "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73",
    ),
)

METRICS: Final = (
    ("SCOPE_CASE_COUNT", "EXACT", "SUM", 1, 475, 1, 1),
    (
        "LOGICAL_DESCRIPTOR_OCCURRENCE_COUNT",
        "SUM",
        "SUM",
        4_294_967_296,
        1_099_511_627_776,
        1_024,
        1_024,
    ),
    (
        "RECURRENCE_STATE_ENTRY_COUNT",
        "SUM",
        "SUM",
        4_194_304,
        268_435_456,
        1_024,
        1_024,
    ),
    (
        "RECURRENCE_TRANSITION_ATTEMPT_COUNT",
        "SUM",
        "SUM",
        134_217_728,
        2_147_483_648,
        1_024,
        1_024,
    ),
    (
        "LOGICAL_UNBATCHED_TRANSITION_EQUIVALENT_COUNT",
        "SUM",
        "SUM",
        1_099_511_627_776,
        281_474_976_710_656,
        1_024,
        1_024,
    ),
    (
        "RECURRENCE_BATCH_APPLICATION_COUNT",
        "SUM",
        "SUM",
        1_048_576,
        134_217_728,
        1_024,
        1_024,
    ),
    (
        "CACHE_ENTRY_COUNT",
        "SUM",
        "SUM",
        1_048_576,
        134_217_728,
        1_024,
        1_024,
    ),
    (
        "CACHE_KEY_CANONICAL_OCTETS",
        "SUM",
        "SUM",
        268_435_456,
        17_179_869_184,
        4_096,
        1_048_576,
    ),
    (
        "DERIVATION_CANONICALIZATION_INPUT_OCTETS",
        "SUM",
        "SUM",
        536_870_912,
        34_359_738_368,
        4_096,
        1_048_576,
    ),
    (
        "DERIVATION_CANONICALIZATION_OUTPUT_OCTETS",
        "SUM",
        "SUM",
        536_870_912,
        34_359_738_368,
        4_096,
        1_048_576,
    ),
    (
        "DERIVATION_HASH_PREIMAGE_OCTETS",
        "SUM",
        "SUM",
        536_870_912,
        34_359_738_368,
        4_096,
        1_048_576,
    ),
    (
        "INTRINSIC_RULE_EVALUATION_COUNT",
        "SUM",
        "SUM",
        134_217_728,
        2_147_483_648,
        1_024,
        1_024,
    ),
    (
        "CROSS_RULE_EVALUATION_COUNT",
        "SUM",
        "SUM",
        134_217_728,
        2_147_483_648,
        1_024,
        1_024,
    ),
    (
        "APPLICATION_EVALUATION_COUNT",
        "SUM",
        "SUM",
        16_777_216,
        536_870_912,
        1_024,
        1_024,
    ),
    ("MAXIMUM_DERIVATION_DEPTH", "MAXIMUM", "MAXIMUM", 65_536, 65_536, 1, 1),
    (
        "MAXIMUM_ITERATION_DEPTH",
        "MAXIMUM",
        "MAXIMUM",
        1_048_576,
        1_048_576,
        1,
        1,
    ),
    (
        "PEAK_RETAINED_DERIVATION_OCTETS",
        "MAXIMUM",
        "MAXIMUM",
        1_073_741_824,
        1_073_741_824,
        4_096,
        4_096,
    ),
    (
        "DERIVATION_RESULT_CANONICAL_OCTETS",
        "SUM",
        "SUM",
        16_773_120,
        4_294_967_296,
        4_096,
        1_048_576,
    ),
)


class CatalogFailure(ValueError):
    """Raised when a pinned authority or derived catalog invariant differs."""


MAXIMUM_JSON_NESTING_DEPTH: Final = 96
MAXIMUM_JSON_STRING_CODEPOINTS: Final = 1_048_576
MAXIMUM_DECODED_JSON_NODE_COUNT: Final = 2_097_152
MAXIMUM_DECODED_JSON_ARRAY_ENTRY_COUNT: Final = 1_048_576
MAXIMUM_DECODED_JSON_OBJECT_MEMBER_COUNT: Final = 1_048_576
MAXIMUM_PINNED_INPUT_OCTETS: Final = 67_108_864
MAXIMUM_INPUT_FILE_COUNT: Final = 64
INDIVIDUAL_FILE_STRICT_UPPER_OCTETS: Final = 16_777_216
OPERATIONAL_OUTPUT_MAXIMUM_OCTETS: Final = 15_728_640


@dataclass(frozen=True)
class _SourceSpec:
    role: str
    path: Path
    exact_octets: int
    raw_sha256: str
    semantic_id: str | None
    json_root_kind: str | None


@dataclass(frozen=True)
class _SourceSnapshot:
    spec: _SourceSpec
    raw: bytes
    identity: tuple[int, int, int, int, int, int, int]
    parent_identity: tuple[int, int, int]


def _fail(message: str) -> NoReturn:
    raise CatalogFailure(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


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


def _repository_relative_parts(path: Path) -> tuple[str, ...]:
    _require(
        not path.is_absolute()
        and bool(path.parts)
        and "\\" not in str(path)
        and path.as_posix() == str(path)
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"{path} is not an exact repository-relative POSIX path",
    )
    return path.parts


def _open_repository_directory_fd(
    root: Path, relative_parts: tuple[str, ...], *, label: str
) -> int:
    _require(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform lacks mandatory secure-directory flags",
    )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(root, flags)
        _require(stat.S_ISDIR(os.fstat(descriptor).st_mode), "root is not a directory")
        for part in relative_parts:
            child = os.open(part, flags, dir_fd=descriptor)
            try:
                _require(
                    stat.S_ISDIR(os.fstat(child).st_mode),
                    f"{label} parent is not a directory",
                )
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (CatalogFailure, OSError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(exc, CatalogFailure):
            raise
        raise CatalogFailure(f"cannot securely open {label} parent") from exc


def _file_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(descriptor: int) -> tuple[int, int, int]:
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), "repository path is not a directory")
    return metadata.st_dev, metadata.st_ino, metadata.st_mode


def _current_directory_identity(
    root: Path, relative_parts: tuple[str, ...], *, label: str
) -> tuple[int, int, int]:
    descriptor = _open_repository_directory_fd(root, relative_parts, label=label)
    try:
        return _directory_identity(descriptor)
    finally:
        os.close(descriptor)


def _bounded_repository_snapshot(root: Path, spec: _SourceSpec) -> _SourceSnapshot:
    _require(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_NONBLOCK"),
        "platform lacks mandatory secure-file flags",
    )
    _require(
        type(spec.exact_octets) is int and spec.exact_octets > 0,
        f"{spec.role} byte bound is invalid",
    )
    _require(
        spec.exact_octets < INDIVIDUAL_FILE_STRICT_UPPER_OCTETS,
        f"{spec.role} reaches the strict individual-file bound",
    )
    parts = _repository_relative_parts(spec.path)
    parent = _open_repository_directory_fd(root, parts[:-1], label=spec.role)
    parent_identity = _directory_identity(parent)
    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(parts[-1], flags, dir_fd=parent)
        try:
            before = os.fstat(descriptor)
            _require(stat.S_ISREG(before.st_mode), f"{spec.path} is not regular")
            _require(before.st_nlink == 1, f"{spec.path} is not single-link")
            _require(before.st_size == spec.exact_octets, f"{spec.path} size differs")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 65_536)
                if not chunk:
                    break
                total += len(chunk)
                _require(total <= spec.exact_octets, f"{spec.path} exceeds its bound")
                chunks.append(chunk)
            after = os.fstat(descriptor)
            _require(
                _file_identity(before) == _file_identity(after),
                f"{spec.path} changed during read",
            )
        finally:
            os.close(descriptor)
        raw = b"".join(chunks)
        _require(len(raw) == spec.exact_octets, f"{spec.path} was truncated")
        _require(_sha256(raw) == spec.raw_sha256, f"{spec.path} hash differs")
        path_metadata = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        _require(
            _file_identity(path_metadata) == _file_identity(after),
            f"{spec.path} path identity changed",
        )
        _require(
            _current_directory_identity(root, parts[:-1], label=spec.role)
            == parent_identity,
            f"{spec.path} parent identity changed",
        )
        return _SourceSnapshot(spec, raw, _file_identity(after), parent_identity)
    finally:
        os.close(parent)


def _snapshot_all_sources(
    root: Path, specs: tuple[_SourceSpec, ...]
) -> dict[Path, _SourceSnapshot]:
    _require(
        0 < len(specs) <= MAXIMUM_INPUT_FILE_COUNT,
        "pinned source count exceeds its F0 ceiling",
    )
    _require(
        sum(spec.exact_octets for spec in specs) <= MAXIMUM_PINNED_INPUT_OCTETS,
        "aggregate pinned input octets exceed their F0 ceiling",
    )
    snapshots: dict[Path, _SourceSnapshot] = {}
    inode_owner: dict[tuple[int, int], Path] = {}
    for spec in specs:
        _require(spec.path not in snapshots, f"duplicate source path: {spec.path}")
        snapshot = _bounded_repository_snapshot(root, spec)
        inode = snapshot.identity[:2]
        _require(
            inode not in inode_owner,
            f"cross-source inode alias: {spec.path} and {inode_owner.get(inode)}",
        )
        inode_owner[inode] = spec.path
        snapshots[spec.path] = snapshot
    return snapshots


def _assert_snapshot_sets_equal(
    first: dict[Path, _SourceSnapshot], second: dict[Path, _SourceSnapshot]
) -> None:
    _require(tuple(first) == tuple(second), "source path order changed")
    for path in first:
        _require(
            first[path] == second[path],
            f"pinned source changed between complete snapshots: {path}",
        )


def _load_repeatable_source_snapshots(
    root: Path, specs: tuple[_SourceSpec, ...]
) -> dict[Path, _SourceSnapshot]:
    first = _snapshot_all_sources(root, specs)
    second = _snapshot_all_sources(root, specs)
    _assert_snapshot_sets_equal(first, second)
    return second


def _reject_json_constant(value: str) -> NoReturn:
    _fail(f"controlled JSON contains non-finite value: {value}")


def _reject_json_float(value: str) -> NoReturn:
    _fail(f"controlled JSON contains a float: {value}")


def _parse_json_integer(value: str) -> int:
    _require(len(value.lstrip("-")) <= 16, "controlled JSON integer is too long")
    parsed = int(value, 10)
    _require(
        -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM,
        "controlled JSON integer exceeds signed safe range",
    )
    return parsed


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"controlled JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _scan_json_before_allocation(text: str) -> None:
    stack: list[str] = []
    closing = {"}": "{", "]": "["}
    position = 0
    in_string = False
    escaped = False
    string_length = 0
    while position < len(text):
        character = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
                _require(
                    string_length <= MAXIMUM_JSON_STRING_CODEPOINTS,
                    "controlled JSON string exceeds its lexical bound",
                )
                string_length = 0
            else:
                _require(
                    ord(character) >= 0x20,
                    "controlled JSON contains an unescaped control character",
                )
                string_length += 1
            position += 1
            continue
        if character == '"':
            in_string = True
            position += 1
            continue
        if character in "[{":
            stack.append(character)
            _require(
                len(stack) <= MAXIMUM_JSON_NESTING_DEPTH,
                "controlled JSON nesting exceeds its lexical bound",
            )
        elif character in "]}":
            _require(
                bool(stack) and stack[-1] == closing[character],
                "controlled JSON delimiters are unbalanced",
            )
            stack.pop()
        elif character == "-" or character.isdigit():
            end = position + 1
            while end < len(text) and text[end] in "0123456789+-.eE":
                end += 1
            token = text[position:end]
            _require(
                len(token.lstrip("-")) <= 16 and not any(c in token for c in ".eE"),
                "controlled JSON numeric token exceeds its lexical policy",
            )
            position = end
            continue
        position += 1
    _require(not in_string and not escaped, "controlled JSON string is unterminated")
    _require(not stack, "controlled JSON container is unterminated")


def _validate_json_scalars(value: Any) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            pending.extend(current.keys())
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
        elif type(current) is str:
            _require(
                not any(0xD800 <= ord(character) <= 0xDFFF for character in current),
                "controlled JSON contains a surrogate code point",
            )
        else:
            _require(
                current is None or type(current) in {bool, int},
                "controlled JSON contains an unsupported scalar",
            )


def _validate_json_complexity(value: Any) -> None:
    pending = [value]
    node_count = 0
    array_entry_count = 0
    object_member_count = 0
    while pending:
        current = pending.pop()
        node_count += 1
        _require(
            node_count <= MAXIMUM_DECODED_JSON_NODE_COUNT,
            "controlled JSON decoded-node count exceeds its F0 ceiling",
        )
        if type(current) is dict:
            object_member_count += len(current)
            _require(
                object_member_count <= MAXIMUM_DECODED_JSON_OBJECT_MEMBER_COUNT,
                "controlled JSON object-member count exceeds its F0 ceiling",
            )
            pending.extend(current.values())
        elif type(current) is list:
            array_entry_count += len(current)
            _require(
                array_entry_count <= MAXIMUM_DECODED_JSON_ARRAY_ENTRY_COUNT,
                "controlled JSON array-entry count exceeds its F0 ceiling",
            )
            pending.extend(current)


def _parse_strict_canonical_json(raw: bytes, *, label: str, root_kind: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogFailure(f"{label} is not UTF-8") from exc
    _scan_json_before_allocation(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
            parse_int=_parse_json_integer,
        )
    except CatalogFailure:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise CatalogFailure(f"{label} is not strict JSON") from exc
    expected_type = {"OBJECT": dict, "ARRAY": list}[root_kind]
    _require(type(value) is expected_type, f"{label} root kind differs")
    _validate_json_scalars(value)
    _validate_json_complexity(value)
    _require(_pretty_bytes(value) == raw, f"{label} is not canonical pretty JSON")
    return value


def _identity_records() -> list[dict[str, Any]]:
    rows = (
        (
            "SEED_CATALOG",
            CATALOG_VERSION,
            CATALOG_DOMAIN,
            (
                "catalog_version",
                "canonicalization_version",
                "measurement_schema_version",
                "protocol_version",
                "identity_envelope_version",
                "ordered_authority_binding_records",
                "ordered_identity_domain_records",
                "unicode_authority_manifest",
                "f0_seed_ceiling_catalog",
                "resource_metric_catalog",
                "recurrence_catalog",
                "logical_event_catalog",
                "case_universe_catalog",
                "logical_plan_recipe_catalog",
                "protocol_counting_semantics_id",
            ),
        ),
        (
            "PROTOCOL_COUNTING_SEMANTICS",
            "riskyieldmm.raw_v8_step2_external_schema_v2.protocol_counting_semantics.v2",
            "RiskYieldMMA2MStep2ExternalSchemaV2ProtocolCountingSemanticsV2V4_9F_RawV8",
            (
                "protocol_version",
                "identity_envelope_version",
                "unicode_authority_manifest_id",
                "f0_seed_ceiling_catalog_id",
                "resource_metric_catalog_id",
                "recurrence_catalog_id",
                "logical_event_catalog_id",
                "case_universe_catalog_id",
                "logical_plan_recipe_catalog_id",
            ),
        ),
        (
            "UNICODE_AUTHORITY_MANIFEST",
            "riskyieldmm.raw_v8_step2_external_schema_v2.unicode_authority_manifest.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2UnicodeAuthorityManifestV1V4_9F_RawV8",
            (
                "unicode_authority_manifest_version",
                "unicode_version",
                "ordered_unicode_source_records",
            ),
        ),
        (
            "F0_SEED_CEILING_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.f0_seed_ceiling_catalog.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2F0SeedCeilingCatalogV1V4_9F_RawV8",
            (
                "catalog_version",
                "ordered_platform_ceiling_records",
                "ordered_publication_ceiling_records",
            ),
        ),
        (
            "RESOURCE_METRIC_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.resource_metric_catalog.v2",
            "RiskYieldMMA2MStep2ExternalSchemaV2ResourceMetricCatalogV2V4_9F_RawV8",
            ("catalog_version", "f2_formula", "ordered_metric_records"),
        ),
        (
            "RECURRENCE_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.recurrence_catalog.v3",
            "RiskYieldMMA2MStep2ExternalSchemaV2RecurrenceCatalogV3V4_9F_RawV8",
            (
                "recurrence_catalog_version",
                "arithmetic_policy",
                "cell_invariant",
                "instruction_set",
                "transfer_rule_catalog",
                "ordered_state_signature_records",
                "cache_key_schema",
                "transition_token_schema",
                "result_cell_schema",
                "step_commitment_schema",
                "ordered_safe_relaxation_records",
                "homogeneous_run_batch_equivalence",
                "ordered_derivation_kernel_records",
                "local_shutdown_analytic_catalog",
            ),
        ),
        (
            "CELL_TRANSFER_RULE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.cell_transfer_rule.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2CellTransferRuleV1V4_9F_RawV8",
            (
                "transfer_rule_version",
                "rule_position",
                "transfer_rule_name",
                "ordered_parameter_names",
                "ordered_parameter_type_records",
                "result_type",
                "program",
            ),
        ),
        (
            "CELL_TRANSFER_RULE_CATALOG",
            (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "cell_transfer_rule_catalog.v1"
            ),
            ("RiskYieldMMA2MStep2ExternalSchemaV2CellTransferRuleCatalogV1V4_9F_RawV8"),
            (
                "transfer_rule_catalog_version",
                "evaluation_order",
                "unknown_or_extra_ast_member_policy",
                "ordered_primitive_opcode_records",
                "ordered_transfer_rule_records",
            ),
        ),
        (
            "LOGICAL_EVENT_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_event_catalog.v2",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalEventCatalogV2V4_9F_RawV8",
            (
                "catalog_version",
                "event_schema",
                "metric_update_schema",
                "ordered_event_kind_records",
                "case_level_event_grammar",
            ),
        ),
        (
            "COUNT_CASE_UNIVERSE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.count_case_universe.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2CountCaseUniverseV1V4_9F_RawV8",
            (
                "catalog_version",
                "maximum_row_count",
                "maximum_row_universe_canonical_json_sha256",
                "contextual_profile_count",
                "contextual_internal_subcase_count",
                "contextual_synthetic_axis_count",
                "verifier_owned_case_count",
                "ordered_case_bindings",
            ),
        ),
        (
            "LOGICAL_PLAN_RECIPE_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_plan_recipe_catalog.v3",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalPlanRecipeCatalogV3V4_9F_RawV8",
            (
                "catalog_version",
                "logical_plan_schema",
                "case_plan_binding_schema",
                "logical_step_schema",
                "profile_conditioned_cell_contract",
                "p2_cross_application_deletion_policy",
                "profile_conditioning_program_schema",
                "logical_plan_instantiation_rule",
                "ordered_logical_plan_templates",
                "ordered_profile_conditioning_program_records",
                "ordered_logical_count_plan_records",
                "ordered_case_plan_bindings",
                "ordered_plan_recipe_records",
            ),
        ),
        (
            "LOGICAL_PLAN_TEMPLATE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_plan_template.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalPlanTemplateV1V4_9F_RawV8",
            (
                "template_version",
                "root_type_name",
                "root_alternative_name",
                "ordered_template_steps",
                "ordered_relaxation_application_records",
                "ordered_required_safe_relaxation_rule_ids",
                "root_step_position",
            ),
        ),
        (
            "LOGICAL_EVENT_STREAM",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_event_stream.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalEventStreamV1V4_9F_RawV8",
            (
                "logical_event_stream_version",
                "logical_count_plan_id",
                "ordered_logical_event_tokens",
            ),
        ),
        (
            "LOCAL_SHUTDOWN_ANALYTIC_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_analytic_catalog.v2",
            "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownAnalyticCatalogV2V4_9F_RawV8",
            (
                "kernel_version",
                "state_signature_id",
                "derivation_kernel_record_sha256",
                "baseline_inventory_json_pointer",
                "baseline_result_inventory_json_pointer",
                "baseline_operation_spec_id",
                "baseline_result_evidence_id",
                "baseline_result_canonical_octets",
                "baseline_attainable_maximum_octets",
                "ordered_mutable_limit_records",
                "ordered_intrinsic_affine_relation_records",
                "ordered_result_counter_mapping_records",
                "ordered_result_array_mapping_records",
                "ordered_optional_sha256_member_names",
                "body_member_syntax_octets",
                "maximizing_fixed_body_octets_excluding_arrays_and_integers",
                "wrapper_overhead_octets",
                "fixed_result_skeleton_octets",
                "array_length_program",
                "raw_unsaturated_wrapper_program",
                "batch_unsaturated_program",
                "batch_saturation_program",
                "batch_saturation_proof",
                "saturated_attainer_program",
                "nested_body_codec_relation",
                "nested_body_codec_octet_limit",
                "masked_outer_codec_relation",
                "masked_outer_codec_octet_limit",
                "ordered_objective_member_names",
                "candidate_enumeration_program",
                "unique_sha256_item_construction_program",
                "controller_instruction_set",
                "controller_metric_count_program",
                "initial_controller_state_position",
                "terminal_controller_state_position",
                "ordered_controller_state_records",
                "ordered_controller_transition_records",
                "winning_member_name",
                "winning_mutated_value",
                "winning_absolute_delta",
                "predecessor_attainable_maximum_octets",
                "winner_attainable_maximum_octets",
                "winner_body_octets",
                "largest_other_one_field_maximum_octets",
                "fixed_controller_state_count",
                "fixed_controller_transition_count",
            ),
        ),
        (
            "STATE_SIGNATURE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.state_signature.v2",
            "RiskYieldMMA2MStep2ExternalSchemaV2StateSignatureV2V4_9F_RawV8",
            ("signature_version", "ordered_component_records"),
        ),
        (
            "LOCAL_SHUTDOWN_CONTROLLER_STATE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_controller_state.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownControllerStateV1V4_9F_RawV8",
            (
                "state_version",
                "state_signature_id",
                "controller_state_position",
                "state_kind",
                "ordered_state_components",
            ),
        ),
        (
            "LOCAL_SHUTDOWN_CONTROLLER_TRANSITION",
            "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_controller_transition.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownControllerTransitionV1V4_9F_RawV8",
            (
                "transition_version",
                "state_signature_id",
                "controller_transition_position",
                "source_controller_state_id",
                "target_controller_state_id",
                "input_mutable_limit_lexical_position",
                "transition_program",
                "candidate_outcome",
                "candidate_objective",
                "expected_target_state_components",
            ),
        ),
        (
            "ARRAY_OBSERVER_CLOSURE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.array_observer_closure.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2ArrayObserverClosureV1V4_9F_RawV8",
            (
                "closure_version",
                "array_value_schema_id",
                "array_typed_path",
                "ordered_observer_records",
                "surviving_state_signature_id",
                "batch_eligible",
                "proof_rule",
            ),
        ),
        (
            "SAFE_RELAXATION_RULE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.safe_relaxation_rule.v2",
            "RiskYieldMMA2MStep2ExternalSchemaV2SafeRelaxationRuleV2V4_9F_RawV8",
            (
                "relaxation_version",
                "relaxation_name",
                "deleted_predicate_class",
                "retained_semantics",
                "soundness_rule",
            ),
        ),
        (
            "HOMOGENEOUS_RUN_BATCH_EQUIVALENCE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.homogeneous_run_batch_equivalence.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2HomogeneousRunBatchEquivalenceV1V4_9F_RawV8",
            (
                "batch_equivalence_version",
                "state_signature_id",
                "identity_state_components",
                "ordered_closed_form_update_records",
                "closed_form_power_record",
                "ordered_absent_observer_kinds",
                "surviving_canonical_boundary_component",
                "small_exhaustive_maximum_cardinality",
                "inductive_law",
            ),
        ),
        (
            "LOGICAL_DERIVATION_STEP",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_derivation_step.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalDerivationStepV1V4_9F_RawV8",
            (
                "template_step_position",
                "derivation_kind",
                "subject_locator",
                "value_schema_id",
                "type_name",
                "alternative_name",
                "ordered_child_step_positions",
                "recurrence_parameters",
                "logical_descriptor_occurrence_count",
                "logical_transfer_multiplicity",
                "physical_transition_count",
                "logical_unbatched_transition_equivalent_count",
                "physical_batch_application_count",
                "ordered_intrinsic_rule_ids",
                "kernel_record_sha256",
                "state_signature_id",
                "cache_key_schema_version",
                "batch_equivalence_id",
            ),
        ),
        (
            "LOGICAL_COUNT_PLAN",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_count_plan.v3",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalCountPlanV3V4_9F_RawV8",
            (
                "logical_count_plan_version",
                "case_position",
                "case_kind",
                "case_binding",
                "upper_bound_mode",
                "recurrence_catalog_id",
                "ordered_safe_relaxation_rule_ids",
                "logical_plan_template_id",
                "profile_conditioning_program_id",
                "local_analytic_catalog_id",
                "logical_root_reference",
                "scope_summary",
                "root_step_position",
            ),
        ),
        (
            "PROFILE_CONDITIONING_PROGRAM",
            "riskyieldmm.raw_v8_step2_external_schema_v2.profile_conditioning_program.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2ProfileConditioningProgramV1V4_9F_RawV8",
            (
                "profile_conditioning_program_version",
                "program_position",
                "case_position",
                "profile_position",
                "maximum_constraint_scope_profile_id",
                "profile_inventory_json_pointer",
                "profile_kind",
                "constraint_scope",
                "operation_kind",
                "conditioning_strategy",
                "measured_type_name",
                "logical_plan_template_id",
                "template_root_step_position",
                "ordered_fixed_authority_operations",
                "scope_root_operation",
                "application_schedule_operation",
                "conditioning_transfer_program",
            ),
        ),
        (
            "PROFILE_CONDITIONED_CELL_CONTRACT",
            "riskyieldmm.raw_v8_step2_external_schema_v2.profile_conditioned_cell_contract.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2ProfileConditionedCellContractV1V4_9F_RawV8",
            (
                "contract_version",
                "p2_cell_ordered_member_names",
                "p2_cell_kind_enum",
                "generic_superset_attainability_claimed",
                "exact_cell_invariant",
                "p1_p3_acceptance_rule",
                "unresolved_or_unattained_policy",
                "structural_bound_only_acceptance_forbidden",
            ),
        ),
        (
            "P2_CROSS_APPLICATION_DELETION_POLICY",
            "riskyieldmm.raw_v8_step2_external_schema_v2.p2_cross_application_deletion_policy.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2P2CrossApplicationDeletionPolicyV1V4_9F_RawV8",
            (
                "policy_version",
                "safe_relaxation_rule_id",
                "deleted_predicate_class",
                "soundness_rule",
                "ordered_rule_application_mapping_records",
            ),
        ),
        (
            "PREFLIGHT_SOURCE_MANIFEST",
            "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_source_manifest.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2PreflightSourceManifestV1V4_9F_RawV8",
            (
                "manifest_version",
                "manifest_phase",
                "ordered_file_records",
                "ordered_program_records",
                "parser_policy",
                "io_policy",
                "watchdog_policy",
                "source_separation_policy",
                "ordered_output_records",
                "declared_input_file_count",
                "declared_total_input_octets",
            ),
        ),
        (
            "PREFLIGHT_SOURCE_FREEZE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_source_freeze.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2PreflightSourceFreezeV1V4_9F_RawV8",
            (
                "freeze_version",
                "source_manifest_repository_relative_path",
                "source_manifest_raw_octet_count",
                "source_manifest_raw_sha256",
                "pre_run_source_manifest_id",
                "freeze_status",
            ),
        ),
        (
            "PREFLIGHT_IMPLEMENTATION",
            "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_implementation.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2PreflightImplementationV1V4_9F_RawV8",
            (
                "implementation_version",
                "implementation_role",
                "repository_relative_path",
                "raw_octet_count",
                "raw_sha256",
                "implementation_strategy",
            ),
        ),
        (
            "HAND_ORACLE_FIXTURE",
            "riskyieldmm.raw_v8_step2_external_schema_v2.hand_oracle_fixture.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2HandOracleFixtureV1V4_9F_RawV8",
            (
                "oracle_position",
                "oracle_name",
                "ordered_coverage_tags",
                "logical_count_plan",
                "ordered_logical_event_tokens",
                "expected_logical_event_stream_sha256",
                "ordered_expected_resource_measurements",
                "expected_status",
            ),
        ),
        (
            "HAND_ORACLE_CATALOG",
            "riskyieldmm.raw_v8_step2_external_schema_v2.hand_oracle_catalog.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2HandOracleCatalogV1V4_9F_RawV8",
            (
                "oracle_catalog_version",
                "seed_catalog_id",
                "ordered_homogeneous_run_oracles",
                "ordered_plan_oracles",
                "ordered_meter_boundary_oracles",
            ),
        ),
        (
            "LOGICAL_CASE_COUNT_RECORD",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_case_count_record.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalCaseCountRecordV1V4_9F_RawV8",
            (
                "case_position",
                "case_kind",
                "case_binding",
                "logical_count_plan_id",
                "ordered_resource_measurements",
                "logical_event_stream_sha256",
            ),
        ),
        (
            "LOGICAL_COUNT_PAYLOAD",
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_count_payload.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2LogicalCountPayloadV1V4_9F_RawV8",
            (
                "schema_version",
                "protocol_counting_semantics_id",
                "ordered_case_count_records",
                "ordered_metric_summary_records",
                "semantic_count_vector_sha256",
            ),
        ),
        (
            "PROTOCOL_BOUND_COUNT_PAYLOAD",
            "riskyieldmm.raw_v8_step2_external_schema_v2.protocol_bound_count_payload.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2ProtocolBoundCountPayloadV1V4_9F_RawV8",
            (
                "schema_version",
                "maximum_protocol_sha256",
                "pre_run_source_manifest_id",
                "ordered_case_protocol_records",
            ),
        ),
        (
            "PREFLIGHT_COMPARISON",
            "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_comparison.v1",
            "RiskYieldMMA2MStep2ExternalSchemaV2PreflightComparisonV1V4_9F_RawV8",
            (
                "comparison_version",
                "pre_run_source_manifest_id",
                "report_a_raw_sha256",
                "report_b_raw_sha256",
                "logical_count_payload_id",
                "protocol_bound_count_payload_id",
                "ordered_case_comparison_records",
                "ordered_metric_comparison_records",
                "source_separation_result",
                "oracle_result",
                "f0_result",
                "comparison_status",
            ),
        ),
    )
    return [
        {
            "identity_position": position,
            "identity_name": name,
            "version_literal": version,
            "domain_literal": domain,
            "ordered_payload_member_names": list(members),
        }
        for position, (name, version, domain, members) in enumerate(rows, 1)
    ]


def _identity_domain(identity_records: list[dict[str, Any]], name: str) -> str:
    matches = [
        row["domain_literal"]
        for row in identity_records
        if row["identity_name"] == name
    ]
    _require(len(matches) == 1, f"identity domain {name} differs")
    return matches[0]


def _unicode_manifest(
    identity_records: list[dict[str, Any]], registry: dict[str, Any]
) -> dict[str, Any]:
    records = registry["unicode_source_catalog"]
    _require(
        type(records) is list and len(records) == 6, "Unicode source catalog differs"
    )
    expected = [(name, octets, digest) for name, octets, digest in UNICODE_SOURCES]
    actual = [
        (record["source_name"], record["byte_count"], record["sha256"])
        for record in records
    ]
    _require(
        actual == expected, "Unicode source order or pins differ from the registry"
    )
    payload = {
        "unicode_authority_manifest_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.unicode_authority_manifest.v1"
        ),
        "unicode_version": "15.0.0",
        "ordered_unicode_source_records": records,
    }
    return {
        **payload,
        "unicode_authority_manifest_id": _semantic_id(
            _identity_domain(identity_records, "UNICODE_AUTHORITY_MANIFEST"), payload
        ),
    }


def _f0_catalog(identity_records: list[dict[str, Any]]) -> dict[str, Any]:
    platform = (
        ("INDIVIDUAL_FILE_STRICT_UPPER_OCTETS", INDIVIDUAL_FILE_STRICT_UPPER_OCTETS),
        ("TOTAL_PINNED_INPUT_OCTETS", MAXIMUM_PINNED_INPUT_OCTETS),
        ("INPUT_FILE_COUNT", MAXIMUM_INPUT_FILE_COUNT),
        ("JSON_NESTING_DEPTH", MAXIMUM_JSON_NESTING_DEPTH),
        ("DECODED_JSON_NODE_COUNT", MAXIMUM_DECODED_JSON_NODE_COUNT),
        ("DECODED_JSON_ARRAY_ENTRY_COUNT", MAXIMUM_DECODED_JSON_ARRAY_ENTRY_COUNT),
        ("DECODED_JSON_OBJECT_MEMBER_COUNT", MAXIMUM_DECODED_JSON_OBJECT_MEMBER_COUNT),
        ("F1_WALL_CLOCK_SECONDS", 14_400),
        ("F1_CPU_SECONDS", 28_800),
        ("F1_PEAK_RSS_OCTETS", 2_147_483_648),
        ("F1_TEMPORARY_STORAGE_OCTETS", 4_294_967_296),
        ("PUBLICATION_STAGING_STORAGE_OCTETS", 8_589_934_592),
    )
    publication = (
        ("SELECTED_ROW_COUNT", 474),
        ("CONTEXT_OBJECT_COUNT", 262_144),
        ("CONTEXT_PAGE_COUNT", 256),
        ("TOTAL_CLOSURE_ENTRY_COUNT", 263_168),
        ("AGGREGATE_ROW_RAW_OCTETS", 2_147_483_648),
        ("AGGREGATE_CONTEXT_COMPACT_OCTETS", 2_147_483_648),
        ("PAGE_MANIFEST_DIRECTORY_METADATA_OCTETS", 536_870_912),
        ("COMPLETE_PUBLISHED_CLOSURE_OCTETS", 4_294_967_296),
        ("PEAK_RETAINED_VALIDATION_OCTETS", 1_073_741_824),
    )
    payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.f0_seed_ceiling_catalog.v1"
        ),
        "ordered_platform_ceiling_records": [
            {"ceiling_position": pos, "resource_name": name, "ceiling_value": value}
            for pos, (name, value) in enumerate(platform, 1)
        ],
        "ordered_publication_ceiling_records": [
            {"ceiling_position": pos, "resource_name": name, "ceiling_value": value}
            for pos, (name, value) in enumerate(publication, 1)
        ],
    }
    return {
        **payload,
        "f0_seed_ceiling_catalog_id": _semantic_id(
            _identity_domain(identity_records, "F0_SEED_CEILING_CATALOG"), payload
        ),
    }


def _metric_catalog(identity_records: list[dict[str, Any]]) -> dict[str, Any]:
    records = [
        {
            "metric_position": position,
            "metric_name": name,
            "per_case_aggregation": per_case,
            "full_run_aggregation": full_run,
            "per_case_f0_ceiling": case_f0,
            "full_run_f0_ceiling": run_f0,
            "per_case_f2_rounding_unit": case_unit,
            "full_run_f2_rounding_unit": run_unit,
        }
        for position, (
            name,
            per_case,
            full_run,
            case_f0,
            run_f0,
            case_unit,
            run_unit,
        ) in enumerate(METRICS, 1)
    ]
    payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.resource_metric_catalog.v2"
        ),
        "f2_formula": "x+((u-(x%u))%u)",
        "ordered_metric_records": records,
    }
    return {
        **payload,
        "resource_metric_catalog_id": _semantic_id(
            _identity_domain(identity_records, "RESOURCE_METRIC_CATALOG"), payload
        ),
    }


def _derive_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for descriptor in registry["ordered_external_type_descriptors"]:
        if descriptor["type_form"] == "RECORD":
            rows.append(
                {
                    "row_position": len(rows) + 1,
                    "row_kind": "INTRINSIC_RECORD",
                    "type_name": descriptor["type_name"],
                    "alternative_name": None,
                    "constraint_scope_profile_id": None,
                }
            )
            continue
        _require(descriptor["type_form"] == "TAGGED_UNION", "unknown type form")
        for alternative in descriptor["tagged_union_descriptor"][
            "ordered_alternatives"
        ]:
            rows.append(
                {
                    "row_position": len(rows) + 1,
                    "row_kind": "INTRINSIC_UNION_ALTERNATIVE",
                    "type_name": descriptor["type_name"],
                    "alternative_name": alternative["alternative_name"],
                    "constraint_scope_profile_id": None,
                }
            )
    _require(len(rows) == 66, "intrinsic row count differs from 66")
    return rows


def _case_universe(
    identity_records: list[dict[str, Any]], inventory: dict[str, Any]
) -> dict[str, Any]:
    rows = _derive_rows(inventory["external_schema_registry_v2"])
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    _require(len(profiles) == 408, "profile count differs from 408")
    for profile in profiles:
        rows.append(
            {
                "row_position": len(rows) + 1,
                "row_kind": profile["profile_kind"],
                "type_name": profile["measured_type_name"],
                "alternative_name": None,
                "constraint_scope_profile_id": profile[
                    "maximum_constraint_scope_profile_id"
                ],
            }
        )
    _require(len(rows) == 474, "publication row count differs from 474")
    _require(
        _sha256(_canonical_bytes(rows)) == MAXIMUM_ROW_UNIVERSE_SHA256,
        "maximum-row universe digest differs",
    )
    case_bindings = [
        {
            "case_position": row["row_position"],
            "case_kind": "MAXIMUM_PUBLICATION_ROW",
            "case_binding": {
                "binding_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_row_count_binding.v1"
                ),
                **row,
            },
        }
        for row in rows
    ]
    case_bindings.append(
        {
            "case_position": 475,
            "case_kind": "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY",
            "case_binding": {
                "binding_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_count_binding.v1"
                ),
                "counterexample_kind": ("LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"),
                "ordinary_maximum_row_position": 69,
                "ordinary_profile_position": 3,
                "constraint_scope_profile_id": LOCAL_PROFILE_ID,
                "baseline_inventory_json_pointer": (
                    "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
                ),
                "baseline_operation_spec_id": BASELINE_OPERATION_SPEC_ID,
                "ordered_mutable_limit_member_names": sorted(
                    row["member_name"]
                    for row in inventory["operation_contracts"][
                        "local_shutdown_scalar_limit_domains"
                    ]
                    if row["member_name"] != "maximum_peer_shutdown_polls"
                ),
                "objective_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_objective.v2"
                ),
                "ordered_objective_member_names": [
                    "changed_limit_field_count",
                    "sum_absolute_integer_deltas",
                    "changed_member_names_in_lexical_order",
                    "resulting_changed_values_in_that_same_order",
                ],
                "masked_codec_coordinate": {
                    "validation_root_type_name": (
                        "CapacityMeasurementOperationResultEvidence"
                    ),
                    "codec_owner_type_name": (
                        "CapacityMeasurementOperationResultEvidence"
                    ),
                    "codec_owner_typed_member_path": [],
                    "codec_byte_bound_relation": "LT",
                    "codec_octet_limit": 524_288,
                },
            },
        }
    )
    payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.count_case_universe.v1"
        ),
        "maximum_row_count": 474,
        "maximum_row_universe_canonical_json_sha256": MAXIMUM_ROW_UNIVERSE_SHA256,
        "contextual_profile_count": 408,
        "contextual_internal_subcase_count": 475,
        "contextual_synthetic_axis_count": 33,
        "verifier_owned_case_count": 475,
        "ordered_case_bindings": case_bindings,
    }
    return {
        **payload,
        "case_universe_catalog_id": _semantic_id(
            _identity_domain(identity_records, "COUNT_CASE_UNIVERSE"), payload
        ),
    }


def _local_batch_unsaturated_wrapper_octets(batch_limit: int) -> int:
    _require(1 <= batch_limit <= 11_731, "batch limit is outside unsaturated region")
    return 2_312 + 268 * batch_limit + len(str(batch_limit))


def _first_local_batch_strict_limit_violation(strict_limit_octets: int) -> int:
    lower = 1
    upper = 11_731
    _require(
        _local_batch_unsaturated_wrapper_octets(upper) >= strict_limit_octets,
        "unsaturated batch region never reaches the strict limit",
    )
    while lower < upper:
        midpoint = lower + (upper - lower) // 2
        if _local_batch_unsaturated_wrapper_octets(midpoint) >= strict_limit_octets:
            upper = midpoint
        else:
            lower = midpoint + 1
    return lower


def _local_candidate_evaluation(
    record: dict[str, Any], *, strict_limit_octets: int
) -> tuple[dict[str, Any], str, int, int, tuple[int, str, int] | None]:
    threshold_class = record["one_field_threshold_class"]
    baseline = record["baseline_value"]
    upper = record["one_field_non_decreasing_upper"]
    endpoint_octets = record["one_field_endpoint_or_cap_maximum_octets"]
    common = {
        "program_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "local_shutdown_candidate_evaluation_program.v1"
        ),
        "baseline_value": baseline,
        "strict_limit_octets": strict_limit_octets,
    }
    if threshold_class == "NO_NONDECREASING_MUTATION":
        _require(upper <= baseline, "non-decreasing mutation interval is not empty")
        _require(
            endpoint_octets < strict_limit_octets, "empty interval endpoint differs"
        )
        program = {
            **common,
            "opcode": "EMPTY_NONDECREASING_INTERVAL_V1",
            "non_decreasing_upper": upper,
            "decisive_attainable_maximum_octets": endpoint_octets,
        }
        return (
            program,
            "EMPTY_NONDECREASING_MUTATION_INTERVAL",
            upper,
            endpoint_octets,
            None,
        )
    if threshold_class == "FAIL":
        _require(upper > baseline, "endpoint candidate has no positive mutation")
        _require(endpoint_octets < strict_limit_octets, "failed endpoint reaches limit")
        program = {
            **common,
            "opcode": "MONOTONE_ENDPOINT_BELOW_STRICT_LIMIT_V1",
            "endpoint_mutated_value": upper,
            "endpoint_attainable_maximum_octets": endpoint_octets,
        }
        return (
            program,
            "ENDPOINT_BELOW_STRICT_OUTER_CODEC_LIMIT",
            upper,
            endpoint_octets,
            None,
        )
    _require(threshold_class == "PASS_BY_BATCH_FORMULA", "unknown threshold class")
    winner = _first_local_batch_strict_limit_violation(strict_limit_octets)
    predecessor = winner - 1
    predecessor_octets = _local_batch_unsaturated_wrapper_octets(predecessor)
    winner_octets = _local_batch_unsaturated_wrapper_octets(winner)
    _require(baseline < winner <= upper, "batch threshold is outside mutation domain")
    _require(
        predecessor_octets < strict_limit_octets <= winner_octets,
        "batch threshold does not straddle strict limit",
    )
    program = {
        **common,
        "opcode": "FIRST_MONOTONE_STRICT_LIMIT_VIOLATION_V1",
        "length_program_locator": "/batch_unsaturated_program",
        "predecessor_mutated_value": predecessor,
        "predecessor_attainable_maximum_octets": predecessor_octets,
        "candidate_mutated_value": winner,
        "candidate_attainable_maximum_octets": winner_octets,
    }
    return (
        program,
        "FIRST_STRICT_OUTER_CODEC_VIOLATION",
        winner,
        winner_octets,
        (winner - baseline, record["member_name"], winner),
    )


def _local_controller_trace(
    identity_records: list[dict[str, Any]],
    mutable_limit_records: list[dict[str, Any]],
    *,
    strict_limit_octets: int,
    state_signature_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_components: list[Any] = [
        0,
        "NOT_EVALUATED",
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    states = [
        {
            "state_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "local_shutdown_controller_state.v1"
            ),
            "state_signature_id": state_signature_id,
            "controller_state_position": 1,
            "state_kind": "INITIAL",
            "ordered_state_components": current_components,
        }
    ]
    transitions: list[dict[str, Any]] = []
    best_objective: tuple[int, str, int] | None = None
    best_record: dict[str, Any] | None = None
    best_value: int | None = None
    best_octets: int | None = None
    for transition_position, record in enumerate(mutable_limit_records, 1):
        _require(
            record["lexical_position"] == transition_position,
            "local mutable-limit lexical positions differ",
        )
        evaluation, outcome, decisive_value, decisive_octets, objective = (
            _local_candidate_evaluation(record, strict_limit_octets=strict_limit_octets)
        )
        update_opcode = "KEEP_NO_ELIGIBLE_BEST_V1"
        if objective is not None and (
            best_objective is None or objective < best_objective
        ):
            update_opcode = (
                "SET_FIRST_ELIGIBLE_BEST_V1"
                if best_objective is None
                else "REPLACE_WITH_LEXICOGRAPHICALLY_SMALLER_BEST_V1"
            )
            best_objective = objective
            best_record = record
            best_value = decisive_value
            best_octets = decisive_octets
        elif objective is not None:
            update_opcode = "KEEP_LEXICOGRAPHICALLY_SMALLER_BEST_V1"
        target_components: list[Any] = [
            transition_position,
            outcome,
            decisive_value,
            decisive_octets,
            None if best_record is None else best_record["lexical_position"],
            best_value,
            None if best_objective is None else best_objective[0],
            best_octets,
        ]
        transitions.append(
            {
                "controller_transition_position": transition_position,
                "source_controller_state_position": transition_position,
                "target_controller_state_position": transition_position + 1,
                "input_mutable_limit_lexical_position": transition_position,
                "transition_program": {
                    "program_version": (
                        "riskyieldmm.raw_v8_step2_external_schema_v2."
                        "local_shutdown_controller_transition_program.v1"
                    ),
                    "opcode": "EVALUATE_ONE_FIELD_AND_FOLD_OBJECTIVE_V1",
                    "candidate_evaluation_program": evaluation,
                    "objective_member_order": [
                        "changed_limit_field_count",
                        "sum_absolute_integer_deltas",
                        "changed_member_names_in_lexical_order",
                        "resulting_changed_values_in_that_same_order",
                    ],
                    "best_update_opcode": update_opcode,
                },
                "candidate_outcome": outcome,
                "candidate_objective": (
                    None
                    if objective is None
                    else {
                        "changed_limit_field_count": 1,
                        "sum_absolute_integer_deltas": objective[0],
                        "changed_member_names_in_lexical_order": [objective[1]],
                        "resulting_changed_values_in_that_same_order": [objective[2]],
                    }
                ),
                "expected_target_state_components": target_components,
            }
        )
        current_components = target_components
        states.append(
            {
                "state_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2."
                    "local_shutdown_controller_state.v1"
                ),
                "state_signature_id": state_signature_id,
                "controller_state_position": transition_position + 1,
                "state_kind": (
                    "TERMINAL"
                    if transition_position == len(mutable_limit_records)
                    else "INTERMEDIATE"
                ),
                "ordered_state_components": current_components,
            }
        )
    _require(len(states) == 12, "local controller state count differs")
    _require(len(transitions) == 11, "local controller transition count differs")
    identified_states = []
    for state in states:
        identified_states.append(
            {
                **state,
                "controller_state_id": _semantic_id(
                    _identity_domain(
                        identity_records, "LOCAL_SHUTDOWN_CONTROLLER_STATE"
                    ),
                    state,
                ),
            }
        )
    identified_transitions = []
    for transition in transitions:
        position = transition["controller_transition_position"]
        transition_payload = {
            "transition_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "local_shutdown_controller_transition.v1"
            ),
            "state_signature_id": state_signature_id,
            "controller_transition_position": position,
            "source_controller_state_id": identified_states[position - 1][
                "controller_state_id"
            ],
            "target_controller_state_id": identified_states[position][
                "controller_state_id"
            ],
            **{
                name: value
                for name, value in transition.items()
                if name
                not in {
                    "controller_transition_position",
                    "source_controller_state_position",
                    "target_controller_state_position",
                }
            },
        }
        identified_transitions.append(
            {
                **transition_payload,
                "controller_transition_id": _semantic_id(
                    _identity_domain(
                        identity_records, "LOCAL_SHUTDOWN_CONTROLLER_TRANSITION"
                    ),
                    transition_payload,
                ),
            }
        )
    return identified_states, identified_transitions


def _local_shutdown_catalog(
    identity_records: list[dict[str, Any]],
    inventory: dict[str, Any],
    *,
    state_signature_id: str,
    derivation_kernel_record_sha256: str,
) -> dict[str, Any]:
    baseline_spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    baseline_result = inventory["fixture_records"]["operation_results"][
        "LOCAL_SHUTDOWN"
    ]
    _require(
        baseline_spec["operation_spec_id"] == BASELINE_OPERATION_SPEC_ID,
        "baseline operation-spec identity differs",
    )
    _require(
        baseline_result["result_evidence_id"] == BASELINE_RESULT_ID,
        "baseline result identity differs",
    )
    _require(
        len(_canonical_bytes(baseline_result)) == 2_504,
        "baseline result length differs",
    )
    body = baseline_spec["spec"]
    domains = inventory["operation_contracts"]["local_shutdown_scalar_limit_domains"]
    domain_by_name = {
        row["member_name"]: (position, row) for position, row in enumerate(domains, 1)
    }
    names = sorted(
        name for name in domain_by_name if name != "maximum_peer_shutdown_polls"
    )
    one_field = {
        "maximum_terminal_ingress_automatic_outputs": (
            1,
            "NO_NONDECREASING_MUTATION",
            2_581,
        ),
        "maximum_terminal_ingress_batches": (
            SAFE_INTEGER_MAXIMUM,
            "PASS_BY_BATCH_FORMULA",
            3_146_277,
        ),
        "maximum_terminal_ingress_ciphertext_octets": (
            SAFE_INTEGER_MAXIMUM,
            "FAIL",
            2_592,
        ),
        "maximum_terminal_ingress_parser_units": (4_096, "FAIL", 276_949),
        "maximum_terminal_ingress_plaintext_octets": (
            16_384,
            "NO_NONDECREASING_MUTATION",
            2_581,
        ),
        "maximum_terminal_socket_receive_calls": (SAFE_INTEGER_MAXIMUM, "FAIL", 2_596),
        "maximum_terminal_tls_records": (1, "NO_NONDECREASING_MUTATION", 2_581),
        "maximum_terminal_tls_unwrap_iterations": (SAFE_INTEGER_MAXIMUM, "FAIL", 2_596),
        "maximum_terminal_zero_progress_iterations": (
            SAFE_INTEGER_MAXIMUM,
            "FAIL",
            2_596,
        ),
        "maximum_tls_control_send_attempts": (256, "FAIL", 2_583),
        "maximum_websocket_send_attempts": (512, "FAIL", 2_583),
    }
    records = []
    for lexical_position, name in enumerate(names, 1):
        domain_position, domain = domain_by_name[name]
        upper, threshold_class, endpoint = one_field[name]
        records.append(
            {
                "lexical_position": lexical_position,
                "authority_domain_position": domain_position,
                "member_name": name,
                "integer_minimum": domain["integer_minimum"],
                "integer_maximum": domain["integer_maximum"],
                "baseline_value": body[name],
                "one_field_non_decreasing_upper": upper,
                "one_field_threshold_class": threshold_class,
                "one_field_endpoint_or_cap_maximum_octets": endpoint,
            }
        )
    strict_outer_limit = 524_288
    registry = inventory["external_schema_registry_v2"]
    descriptor_by_name = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    local_intrinsic_rule_ids = [
        *descriptor_by_name["CapacityMeasurementLocalShutdownSpecV2"][
            "ordered_intrinsic_rule_ids"
        ],
        *descriptor_by_name["CapacityMeasurementLocalShutdownResultEvidenceV2"][
            "ordered_intrinsic_rule_ids"
        ],
    ]
    _require(len(local_intrinsic_rule_ids) == 2, "local intrinsic-rule count differs")
    local_application = next(
        row
        for row in registry["ordered_rule_application_descriptors"]
        if row["application_name"] == "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
    )
    _require(
        local_application["rule_id"] == "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1",
        "local cross-rule binding differs",
    )
    controller_states, controller_transitions = _local_controller_trace(
        identity_records,
        records,
        strict_limit_octets=strict_outer_limit,
        state_signature_id=state_signature_id,
    )
    terminal_components = controller_states[-1]["ordered_state_components"]
    _require(
        terminal_components
        == [
            11,
            "ENDPOINT_BELOW_STRICT_OUTER_CODEC_LIMIT",
            512,
            2_583,
            2,
            1_948,
            1_947,
            524_380,
        ],
        "local controller terminal state differs",
    )

    def parameter(name: str) -> dict[str, Any]:
        return {"opcode": "PARAM_U128", "parameter_name": name}

    def constant(value: int) -> dict[str, Any]:
        return {"opcode": "CONST_U128", "value": value}

    def add(*values: dict[str, Any]) -> dict[str, Any]:
        return {"opcode": "CHECKED_ADD", "ordered_operands": list(values)}

    def multiply(*values: dict[str, Any]) -> dict[str, Any]:
        return {"opcode": "CHECKED_MUL", "ordered_operands": list(values)}

    relation_programs = {
        "maximum_terminal_ingress_plaintext_octets<=16384*maximum_terminal_ingress_batches": (
            parameter("maximum_terminal_ingress_plaintext_octets"),
            multiply(constant(16_384), parameter("maximum_terminal_ingress_batches")),
        ),
        "2*maximum_terminal_ingress_parser_units<=maximum_terminal_ingress_plaintext_octets": (
            multiply(constant(2), parameter("maximum_terminal_ingress_parser_units")),
            parameter("maximum_terminal_ingress_plaintext_octets"),
        ),
        "maximum_terminal_tls_records<=maximum_terminal_ingress_batches": (
            parameter("maximum_terminal_tls_records"),
            parameter("maximum_terminal_ingress_batches"),
        ),
        "maximum_terminal_ingress_automatic_outputs<=maximum_terminal_ingress_parser_units": (
            parameter("maximum_terminal_ingress_automatic_outputs"),
            parameter("maximum_terminal_ingress_parser_units"),
        ),
        "maximum_websocket_send_attempts<=256*(1+maximum_terminal_ingress_automatic_outputs)": (
            parameter("maximum_websocket_send_attempts"),
            multiply(
                constant(256),
                add(
                    constant(1),
                    parameter("maximum_terminal_ingress_automatic_outputs"),
                ),
            ),
        ),
    }
    authority_relation_literals = inventory["operation_contracts"][
        "local_shutdown_intrinsic_limit_relations"
    ]
    _require(
        set(authority_relation_literals) == set(relation_programs),
        "local intrinsic-relation authority differs",
    )
    structured_relation_records = [
        {
            "relation_position": position,
            "authority_relation_literal": literal,
            "relation_program": {
                "program_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2."
                    "local_shutdown_intrinsic_relation_program.v1"
                ),
                "opcode": "CHECK_LE_U128_V1",
                "left_expression": relation_programs[literal][0],
                "right_expression": relation_programs[literal][1],
            },
        }
        for position, literal in enumerate(authority_relation_literals, 1)
    ]
    payload = {
        "kernel_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_analytic_length_sweep.v2"
        ),
        "state_signature_id": state_signature_id,
        "derivation_kernel_record_sha256": derivation_kernel_record_sha256,
        "baseline_inventory_json_pointer": (
            "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
        ),
        "baseline_result_inventory_json_pointer": (
            "/fixture_records/operation_results/LOCAL_SHUTDOWN"
        ),
        "baseline_operation_spec_id": BASELINE_OPERATION_SPEC_ID,
        "baseline_result_evidence_id": BASELINE_RESULT_ID,
        "baseline_result_canonical_octets": 2_504,
        "baseline_attainable_maximum_octets": 2_581,
        "ordered_mutable_limit_records": records,
        "ordered_intrinsic_affine_relation_records": structured_relation_records,
        "ordered_result_counter_mapping_records": [
            {
                "mapping_position": 1,
                "result_member": "shutdown_trace_step_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SAFE_INTEGER_MAXIMUM",
                "spec_member": None,
            },
            {
                "mapping_position": 2,
                "result_member": "final_terminal_ingress_batch_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_MIN_SPEC_AND_ARRAY_MAXIMUM",
                "spec_member": "maximum_terminal_ingress_batches",
            },
            {
                "mapping_position": 3,
                "result_member": "final_terminal_ingress_ciphertext_octets",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_ingress_ciphertext_octets",
            },
            {
                "mapping_position": 4,
                "result_member": "final_terminal_ingress_plaintext_octets",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_ingress_plaintext_octets",
            },
            {
                "mapping_position": 5,
                "result_member": "final_terminal_socket_receive_call_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_socket_receive_calls",
            },
            {
                "mapping_position": 6,
                "result_member": "final_terminal_tls_record_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_tls_records",
            },
            {
                "mapping_position": 7,
                "result_member": "final_terminal_tls_unwrap_iteration_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_tls_unwrap_iterations",
            },
            {
                "mapping_position": 8,
                "result_member": "final_terminal_zero_progress_iteration_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_zero_progress_iterations",
            },
            {
                "mapping_position": 9,
                "result_member": "final_terminal_ingress_parser_unit_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_ingress_parser_units",
            },
            {
                "mapping_position": 10,
                "result_member": "final_terminal_ingress_automatic_output_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_terminal_ingress_automatic_outputs",
            },
            {
                "mapping_position": 11,
                "result_member": "final_websocket_send_attempt_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_websocket_send_attempts",
            },
            {
                "mapping_position": 12,
                "result_member": "final_tls_control_send_attempt_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_tls_control_send_attempts",
            },
            {
                "mapping_position": 13,
                "result_member": "final_peer_shutdown_poll_count",
                "source_kind": "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                "spec_member": "maximum_peer_shutdown_polls",
            },
        ],
        "ordered_result_array_mapping_records": [
            {
                "mapping_position": position,
                "result_member": name,
                "cardinality_source": source,
                "schema_maximum_items": maximum,
            }
            for position, (name, source, maximum) in enumerate(
                (
                    (
                        "ordered_terminal_ingress_read_attempt_event_ids",
                        "maximum_terminal_ingress_batches",
                        524_288,
                    ),
                    (
                        "ordered_terminal_ingress_read_result_event_ids",
                        "maximum_terminal_ingress_batches",
                        524_288,
                    ),
                    (
                        "ordered_terminal_raw_ingress_commit_ids",
                        "maximum_terminal_ingress_batches",
                        524_288,
                    ),
                    (
                        "ordered_terminal_raw_ingress_actor_event_ids",
                        "maximum_terminal_ingress_batches",
                        524_288,
                    ),
                    (
                        "ordered_terminal_parser_transition_event_ids",
                        "maximum_terminal_ingress_parser_units",
                        4_096,
                    ),
                ),
                1,
            )
        ],
        "ordered_optional_sha256_member_names": [
            "local_close_dispatch_completion_event_id",
            "local_shutdown_deadline_evidence_event_id",
            "websocket_close_received_transition_event_id",
        ],
        "body_member_syntax_octets": 1_110,
        "maximizing_fixed_body_octets_excluding_arrays_and_integers": 1_656,
        "wrapper_overhead_octets": 549,
        "fixed_result_skeleton_octets": 2_205,
        "array_length_program": {
            "opcode": "SHA256_ARRAY_CANONICAL_OCTETS_V1",
            "zero_cardinality_octets": 2,
            "positive_cardinality_linear_coefficient": 67,
            "positive_cardinality_constant_octets": 1,
        },
        "raw_unsaturated_wrapper_program": {
            "opcode": "CHECKED_AFFINE_SUM_V1",
            "constant_octets": 2_210,
            "ordered_variable_terms": [
                {"variable": "BATCH_ARRAY_CARDINALITY_N", "coefficient": 268},
                {"variable": "PARSER_ARRAY_CARDINALITY_Q", "coefficient": 67},
                {"variable": "INTEGER_LEXEME_OCTETS_D", "coefficient": 1},
            ],
        },
        "batch_unsaturated_program": {
            "opcode": "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1",
            "constant_octets": 2_312,
            "linear_variable": "MAXIMUM_TERMINAL_INGRESS_BATCHES",
            "linear_coefficient": 268,
            "decimal_width_coefficient": 1,
            "valid_minimum": 1,
            "valid_maximum": 11_731,
        },
        "batch_saturation_program": {
            "opcode": "NESTED_BODY_CAP_ATTAINMENT_V1",
            "first_saturated_batch_limit": 11_732,
            "attainable_wrapper_octets": 3_146_277,
        },
        "batch_saturation_proof": {
            "first_saturated_batch_limit": 11_732,
            "last_unsaturated_batch_limit": 11_731,
            "last_unsaturated_wrapper_octets": 3_146_225,
            "attaining_read_attempt_array_items": 11_732,
            "attaining_read_result_array_items": 11_732,
            "attaining_raw_commit_array_items": 11_731,
            "attaining_raw_actor_array_items": 11_731,
            "attaining_parser_transition_array_items": 1,
            "attaining_nonnull_optional_sha256_count": 2,
            "attaining_null_optional_sha256_count": 1,
            "attaining_shutdown_trace_step_count": 1_000,
            "attaining_integer_lexeme_octets": 20,
            "attaining_body_octets": 3_145_728,
            "attaining_wrapper_octets": 3_146_277,
            "attainment_component_octets": {
                "fixed_non_array_non_integer_octets": 1_594,
                "paired_array_linear_coefficient": 134,
                "paired_array_cardinality_sum": 23_463,
                "parser_and_array_constant_octets": 72,
                "integer_lexeme_octets": 20,
                "total_body_octets": 3_145_728,
            },
            "unique_item_construction_program": {
                "opcode": "LOWERCASE_HEX_ZERO_PAD_FIXED_WIDTH_V1",
                "input_variable": "ZERO_BASED_ITEM_ORDINAL",
                "minimum_input_value": 0,
                "output_code_unit_width": 64,
                "alphabet": "0123456789abcdef",
            },
        },
        "saturated_attainer_program": {
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "local_shutdown_saturated_attainer_program.v1"
            ),
            "ordered_array_cardinality_records": [
                {
                    "member_name": "ordered_terminal_ingress_read_attempt_event_ids",
                    "cardinality": 11_732,
                },
                {
                    "member_name": "ordered_terminal_ingress_read_result_event_ids",
                    "cardinality": 11_732,
                },
                {
                    "member_name": "ordered_terminal_raw_ingress_commit_ids",
                    "cardinality": 11_731,
                },
                {
                    "member_name": "ordered_terminal_raw_ingress_actor_event_ids",
                    "cardinality": 11_731,
                },
                {
                    "member_name": "ordered_terminal_parser_transition_event_ids",
                    "cardinality": 1,
                },
            ],
            "ordered_optional_sha256_state_records": [
                {
                    "member_name": "local_close_dispatch_completion_event_id",
                    "state": "NON_NULL_DISTINCT_LOWERCASE_SHA256",
                },
                {
                    "member_name": "local_shutdown_deadline_evidence_event_id",
                    "state": "NULL",
                },
                {
                    "member_name": "websocket_close_received_transition_event_id",
                    "state": "NON_NULL_DISTINCT_LOWERCASE_SHA256",
                },
            ],
            "ordered_counter_value_records": [
                {"member_name": "shutdown_trace_step_count", "value": 1_000},
                {"member_name": "final_terminal_ingress_batch_count", "value": 11_732},
                {"member_name": "final_terminal_ingress_ciphertext_octets", "value": 0},
                {"member_name": "final_terminal_ingress_plaintext_octets", "value": 0},
                {"member_name": "final_terminal_socket_receive_call_count", "value": 0},
                {"member_name": "final_terminal_tls_record_count", "value": 0},
                {
                    "member_name": "final_terminal_tls_unwrap_iteration_count",
                    "value": 0,
                },
                {
                    "member_name": "final_terminal_zero_progress_iteration_count",
                    "value": 0,
                },
                {"member_name": "final_terminal_ingress_parser_unit_count", "value": 1},
                {
                    "member_name": "final_terminal_ingress_automatic_output_count",
                    "value": 0,
                },
                {"member_name": "final_websocket_send_attempt_count", "value": 0},
                {"member_name": "final_tls_control_send_attempt_count", "value": 0},
                {"member_name": "final_peer_shutdown_poll_count", "value": 0},
            ],
            "required_sha256_item_program": {
                "opcode": "LOWERCASE_HEX_ZERO_PAD_FIXED_WIDTH_V1",
                "input_variable": "ZERO_BASED_ITEM_ORDINAL",
                "minimum_input_value": 0,
                "output_code_unit_width": 64,
                "alphabet": "0123456789abcdef",
            },
            "terminal_outcome_source": "BASELINE_EXPECTED_TERMINAL_OUTCOME",
            "result_evidence_id_program": {
                "opcode": "RECOMPUTE_SEMANTIC_ID_FROM_COMPLETE_OWNER_PAYLOAD_V1",
                "identity_domain_role": "CAPACITY_MEASUREMENT_OPERATION_RESULT_EVIDENCE",
            },
        },
        "nested_body_codec_relation": "LE",
        "nested_body_codec_octet_limit": 3_145_728,
        "masked_outer_codec_relation": "LT",
        "masked_outer_codec_octet_limit": strict_outer_limit,
        "ordered_objective_member_names": [
            "changed_limit_field_count",
            "sum_absolute_integer_deltas",
            "changed_member_names_in_lexical_order",
            "resulting_changed_values_in_that_same_order",
        ],
        "candidate_enumeration_program": {
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "local_shutdown_candidate_enumeration_program.v1"
            ),
            "opcode": "LEXICAL_ONE_FIELD_NONDECREASING_SWEEP_V1",
            "candidate_source_locator": "/ordered_mutable_limit_records",
            "fixed_changed_limit_field_count": 1,
            "mutation_direction": "NONDECREASING",
            "baseline_excluded": True,
            "selection_opcode": "LEXICOGRAPHIC_MIN_OBJECTIVE_V1",
        },
        "unique_sha256_item_construction_program": {
            "opcode": "LOWERCASE_HEX_ZERO_PAD_FIXED_WIDTH_V1",
            "input_variable": "ZERO_BASED_ITEM_ORDINAL",
            "minimum_input_value": 0,
            "output_code_unit_width": 64,
            "alphabet": "0123456789abcdef",
        },
        "controller_instruction_set": {
            "instruction_set_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "local_shutdown_controller_instruction_set.v1"
            ),
            "unknown_or_extra_member_policy": "REJECT",
            "ordered_state_component_kinds": [
                "PROCESSED_MUTABLE_LIMIT_COUNT",
                "CURRENT_CANDIDATE_OUTCOME",
                "CURRENT_DECISIVE_MUTATED_VALUE",
                "CURRENT_DECISIVE_ATTAINABLE_MAXIMUM_OCTETS",
                "BEST_CANDIDATE_LEXICAL_POSITION",
                "BEST_CANDIDATE_MUTATED_VALUE",
                "BEST_CANDIDATE_ABSOLUTE_DELTA",
                "BEST_CANDIDATE_ATTAINABLE_MAXIMUM_OCTETS",
            ],
            "candidate_outcome_enum": [
                "NOT_EVALUATED",
                "EMPTY_NONDECREASING_MUTATION_INTERVAL",
                "ENDPOINT_BELOW_STRICT_OUTER_CODEC_LIMIT",
                "FIRST_STRICT_OUTER_CODEC_VIOLATION",
            ],
            "ordered_candidate_evaluation_opcode_records": [
                {
                    "opcode_position": 1,
                    "opcode": "EMPTY_NONDECREASING_INTERVAL_V1",
                    "ordered_required_member_names_after_opcode": [
                        "program_version",
                        "baseline_value",
                        "strict_limit_octets",
                        "non_decreasing_upper",
                        "decisive_attainable_maximum_octets",
                    ],
                },
                {
                    "opcode_position": 2,
                    "opcode": "MONOTONE_ENDPOINT_BELOW_STRICT_LIMIT_V1",
                    "ordered_required_member_names_after_opcode": [
                        "program_version",
                        "baseline_value",
                        "strict_limit_octets",
                        "endpoint_mutated_value",
                        "endpoint_attainable_maximum_octets",
                    ],
                },
                {
                    "opcode_position": 3,
                    "opcode": "FIRST_MONOTONE_STRICT_LIMIT_VIOLATION_V1",
                    "ordered_required_member_names_after_opcode": [
                        "program_version",
                        "baseline_value",
                        "strict_limit_octets",
                        "length_program_locator",
                        "predecessor_mutated_value",
                        "predecessor_attainable_maximum_octets",
                        "candidate_mutated_value",
                        "candidate_attainable_maximum_octets",
                    ],
                },
            ],
            "controller_transition_opcode_record": {
                "opcode": "EVALUATE_ONE_FIELD_AND_FOLD_OBJECTIVE_V1",
                "ordered_required_member_names_after_opcode": [
                    "program_version",
                    "candidate_evaluation_program",
                    "objective_member_order",
                    "best_update_opcode",
                ],
            },
            "best_update_opcode_enum": [
                "KEEP_NO_ELIGIBLE_BEST_V1",
                "SET_FIRST_ELIGIBLE_BEST_V1",
                "KEEP_LEXICOGRAPHICALLY_SMALLER_BEST_V1",
                "REPLACE_WITH_LEXICOGRAPHICALLY_SMALLER_BEST_V1",
            ],
            "intrinsic_relation_program_schema": {
                "ordered_member_names": [
                    "program_version",
                    "opcode",
                    "left_expression",
                    "right_expression",
                ],
                "opcode_enum": ["CHECK_LE_U128_V1"],
                "expression_schema_source": (
                    "/recurrence_catalog/instruction_set/u128_expression_schema"
                ),
                "evaluation_result_type": "BOOLEAN",
            },
            "controller_state_schema": {
                "ordered_member_names": [
                    "state_version",
                    "state_signature_id",
                    "controller_state_position",
                    "state_kind",
                    "ordered_state_components",
                    "controller_state_id",
                ],
                "state_kind_enum": ["INITIAL", "INTERMEDIATE", "TERMINAL"],
            },
            "controller_transition_schema": {
                "ordered_member_names": [
                    "transition_version",
                    "state_signature_id",
                    "controller_transition_position",
                    "source_controller_state_id",
                    "target_controller_state_id",
                    "input_mutable_limit_lexical_position",
                    "transition_program",
                    "candidate_outcome",
                    "candidate_objective",
                    "expected_target_state_components",
                    "controller_transition_id",
                ],
            },
        },
        "controller_metric_count_program": {
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "local_shutdown_controller_metric_count_program.v1"
            ),
            "ordered_exact_non_byte_metric_records": [
                {
                    "metric_position": position,
                    "metric_name": METRICS[position - 1][0],
                    "value_opcode": opcode,
                    "expected_value": value,
                    "ordered_authority_values": authority_values,
                }
                for position, opcode, value, authority_values in (
                    (1, "CONST_U128", 1, [1]),
                    (2, "CONTROLLER_TRANSITION_COUNT", 11, [11]),
                    (3, "CONTROLLER_STATE_COUNT", 12, [12]),
                    (4, "CONTROLLER_TRANSITION_COUNT", 11, [11]),
                    (5, "CONTROLLER_TRANSITION_COUNT", 11, [11]),
                    (6, "CONST_U128", 0, [0]),
                    (7, "CONTROLLER_STATE_COUNT", 12, [12]),
                    (
                        12,
                        "ORDERED_INTRINSIC_RULE_ID_COUNT",
                        2,
                        local_intrinsic_rule_ids,
                    ),
                    (
                        13,
                        "ORDERED_CROSS_RULE_ID_COUNT",
                        1,
                        [local_application["rule_id"]],
                    ),
                    (
                        14,
                        "ORDERED_APPLICATION_ID_COUNT",
                        1,
                        [local_application["rule_application_id"]],
                    ),
                    (15, "CONST_U128", 1, [1]),
                    (16, "CONTROLLER_TRANSITION_COUNT", 11, [11]),
                )
            ],
            "ordered_runtime_byte_metric_positions": [8, 9, 10, 11, 17, 18],
            "runtime_byte_metric_opcode": (
                "RECOMPUTE_FROM_FINAL_BOUND_RUNTIME_CANONICAL_OBJECTS_V1"
            ),
            "runtime_byte_metric_seed_value_claimed": False,
        },
        "initial_controller_state_position": 1,
        "terminal_controller_state_position": 12,
        "ordered_controller_state_records": controller_states,
        "ordered_controller_transition_records": controller_transitions,
        "winning_member_name": "maximum_terminal_ingress_batches",
        "winning_mutated_value": 1_948,
        "winning_absolute_delta": 1_947,
        "predecessor_attainable_maximum_octets": 524_112,
        "winner_attainable_maximum_octets": 524_380,
        "winner_body_octets": 523_831,
        "largest_other_one_field_maximum_octets": 276_949,
        "fixed_controller_state_count": 12,
        "fixed_controller_transition_count": 11,
    }
    return {
        **payload,
        "local_shutdown_analytic_catalog_id": _semantic_id(
            _identity_domain(identity_records, "LOCAL_SHUTDOWN_ANALYTIC_CATALOG"),
            payload,
        ),
    }


def _state_signature(
    identity_records: list[dict[str, Any]],
    *,
    position: int,
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "signature_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.state_signature.v2"
        ),
        "ordered_component_records": components,
    }
    return {
        "signature_position": position,
        **payload,
        "state_signature_id": _semantic_id(
            _identity_domain(identity_records, "STATE_SIGNATURE"), payload
        ),
    }


def _normalize_transfer_ast(
    value: Any, required_members_by_opcode: dict[str, list[str]]
) -> Any:
    if isinstance(value, list):
        return [
            _normalize_transfer_ast(item, required_members_by_opcode) for item in value
        ]
    if not isinstance(value, dict):
        return value
    if "opcode" not in value:
        return {
            key: _normalize_transfer_ast(child, required_members_by_opcode)
            for key, child in value.items()
        }
    opcode = value["opcode"]
    _require(
        type(opcode) is str and opcode in required_members_by_opcode,
        "unknown transfer AST opcode",
    )
    required = required_members_by_opcode[opcode]
    _require(
        set(value) == {"opcode", *required},
        f"transfer AST member set differs: {opcode}",
    )
    return {
        "opcode": opcode,
        **{
            name: _normalize_transfer_ast(value[name], required_members_by_opcode)
            for name in required
        },
    }


def _called_transfer_rule_ids(value: Any) -> list[str]:
    called: list[str] = []
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            if current.get("opcode") == "CALL_RULE_V1":
                transfer_rule_id = current.get("transfer_rule_id")
                _require(
                    type(transfer_rule_id) is str,
                    "transfer AST call has no exact rule identity",
                )
                called.append(transfer_rule_id)
            pending.extend(reversed(list(current.values())))
        elif type(current) is list:
            pending.extend(reversed(current))
    return called


def _validated_transfer_rule_catalog(
    raw: bytes, identity_records: list[dict[str, Any]]
) -> dict[str, Any]:
    value = _parse_strict_canonical_json(
        raw, label="cell-transfer rule catalog", root_kind="OBJECT"
    )
    _require(type(value) is dict, "cell-transfer rule catalog root is not an object")
    _require(
        list(value)
        == [
            "evaluation_order",
            "ordered_primitive_opcode_records",
            "ordered_transfer_rule_records",
            "transfer_rule_catalog_id",
            "transfer_rule_catalog_version",
            "unknown_or_extra_ast_member_policy",
        ],
        "cell-transfer rule catalog member order differs",
    )
    _require(
        value["transfer_rule_catalog_version"]
        == ("riskyieldmm.raw_v8_step2_external_schema_v2.cell_transfer_rule_catalog.v1")
        and value["evaluation_order"]
        == "DEPTH_FIRST_LEFT_TO_RIGHT_LAZY_BRANCHES_CHECKED_UINT128"
        and value["unknown_or_extra_ast_member_policy"] == "REJECT",
        "cell-transfer catalog execution contract differs",
    )
    # Source JSON is key-sorted. Rebuild semantic payloads in identity order;
    # canonical identity is independent of object insertion order.
    rules = value["ordered_transfer_rule_records"]
    _require(type(rules) is list and bool(rules), "cell-transfer rules are absent")
    primitives = value["ordered_primitive_opcode_records"]
    _require(
        type(primitives) is list and bool(primitives),
        "cell-transfer primitive opcodes are absent",
    )
    primitive_member_names = {
        "opcode_position",
        "opcode",
        "ordered_required_member_names_after_opcode",
        "operand_type_rule",
        "result_type",
        "unknown_or_extra_member_policy",
    }
    for position, row in enumerate(primitives, 1):
        _require(
            type(row) is dict and set(row) == primitive_member_names,
            "cell-transfer primitive schema differs",
        )
        required_names = row["ordered_required_member_names_after_opcode"]
        _require(
            row["opcode_position"] == position
            and type(row["opcode"]) is str
            and bool(row["opcode"])
            and type(required_names) is list
            and all(type(name) is str and name != "opcode" for name in required_names)
            and len(set(required_names)) == len(required_names)
            and type(row["operand_type_rule"]) is str
            and type(row["result_type"]) is str
            and row["unknown_or_extra_member_policy"] == "REJECT",
            "cell-transfer primitive contract differs",
        )
    required_members_by_opcode = {
        row["opcode"]: row["ordered_required_member_names_after_opcode"]
        for row in primitives
    }
    _require(
        len(required_members_by_opcode) == len(primitives),
        "duplicate cell-transfer primitive opcode",
    )
    rule_identity = next(
        row for row in identity_records if row["identity_name"] == "CELL_TRANSFER_RULE"
    )
    catalog_identity = next(
        row
        for row in identity_records
        if row["identity_name"] == "CELL_TRANSFER_RULE_CATALOG"
    )
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    normalized_rules: list[dict[str, Any]] = []
    allowed_parameter_types = {
        "BOOLEAN_OR_NULL_FULL_DOMAIN_SENTINEL",
        "JSON_MAPPING",
        "OPTIONAL_TEXT",
        "OPTIONAL_U128",
        "ORDERED_JSON_ARRAY",
        "SIGNED_SAFE_INTEGER",
        "TEXT",
        "TYPED_PATH",
        "U128",
    }
    for position, rule in enumerate(rules, 1):
        _require(type(rule) is dict, "cell-transfer rule is not an object")
        _require(
            set(rule)
            == {*rule_identity["ordered_payload_member_names"], "transfer_rule_id"},
            "cell-transfer rule member set differs",
        )
        _require(rule.get("rule_position") == position, "transfer-rule order differs")
        parameter_names = rule.get("ordered_parameter_names")
        parameter_types = rule.get("ordered_parameter_type_records")
        _require(
            rule.get("transfer_rule_version") == rule_identity["version_literal"]
            and type(parameter_names) is list
            and all(type(name) is str and bool(name) for name in parameter_names)
            and len(set(parameter_names)) == len(parameter_names)
            and type(parameter_types) is list
            and len(parameter_types) == len(parameter_names)
            and rule.get("result_type") == "CELL",
            "cell-transfer rule signature differs",
        )
        for parameter_position, (parameter_name, parameter_record) in enumerate(
            zip(parameter_names, parameter_types, strict=True), 1
        ):
            _require(
                type(parameter_record) is dict
                and set(parameter_record)
                == {"parameter_position", "parameter_name", "value_type"}
                and parameter_record["parameter_position"] == parameter_position
                and parameter_record["parameter_name"] == parameter_name
                and parameter_record["value_type"] in allowed_parameter_types,
                "cell-transfer parameter contract differs",
            )
        payload = {
            name: (
                _normalize_transfer_ast(rule[name], required_members_by_opcode)
                if name == "program"
                else rule[name]
            )
            for name in rule_identity["ordered_payload_member_names"]
        }
        expected_id = _semantic_id(rule_identity["domain_literal"], payload)
        _require(
            rule.get("transfer_rule_id") == expected_id, "transfer-rule ID differs"
        )
        name = rule.get("transfer_rule_name")
        _require(
            type(name) is str and name not in seen_names, "transfer-rule name differs"
        )
        _require(expected_id not in seen_ids, "duplicate transfer-rule ID")
        _require(
            set(_called_transfer_rule_ids(payload["program"])) <= seen_ids,
            "transfer-rule call is unresolved, self-referential, or forward",
        )
        seen_names.add(name)
        seen_ids.add(expected_id)
        normalized_rules.append({**payload, "transfer_rule_id": expected_id})
    payload = {
        name: (
            normalized_rules if name == "ordered_transfer_rule_records" else value[name]
        )
        for name in catalog_identity["ordered_payload_member_names"]
    }
    _require(
        value.get("transfer_rule_catalog_id")
        == _semantic_id(catalog_identity["domain_literal"], payload),
        "cell-transfer rule catalog ID differs",
    )
    _require(
        set(_TRANSFER_RULE_NAME_BY_OPCODE.values()) <= seen_names,
        "opcode-to-transfer-rule mapping is unresolved",
    )
    return {
        **payload,
        "transfer_rule_catalog_id": value["transfer_rule_catalog_id"],
    }


def _instruction_set(transfer_rule_catalog: dict[str, Any]) -> dict[str, Any]:
    rule_by_name = {
        row["transfer_rule_name"]: row
        for row in transfer_rule_catalog["ordered_transfer_rule_records"]
    }
    expression_rows = (
        ("CONST_U128", ("value",)),
        ("STEP_LOGICAL_TRANSFER_MULTIPLICITY", ()),
        ("PARAM_U128", ("parameter_name",)),
        ("PARAM_LIST_COUNT", ("parameter_name",)),
        ("INDICATOR_PARAM_NONZERO", ("parameter_name",)),
        ("CHECKED_ADD", ("ordered_operands",)),
        ("CHECKED_MUL", ("ordered_operands",)),
        ("INDICATOR_PARAM_IS_NULL", ("parameter_name",)),
    )
    return {
        "instruction_set_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "closed_recurrence_instruction_set.v1"
        ),
        "cell_contract": {
            "ordered_member_names": [
                "cell_status",
                "certified_lower_bound_octets",
                "certified_upper_bound_octets",
                "ordered_state_components",
            ],
            "empty_normal_form": {
                "cell_status": "PROVABLY_EMPTY",
                "certified_lower_bound_octets": 0,
                "certified_upper_bound_octets": 0,
                "state_components_source": "DECLARED_STATE_SIGNATURE_IDENTITY",
            },
            "nonempty_invariant": (
                "ZERO_LE_LOWER_LE_UPPER_LE_EFFECTIVE_CEILING_AND_"
                "ALL_RELAXED_VALUES_WITHIN_BOUNDS"
            ),
            "intermediate_attainability_claimed": False,
        },
        "u128_expression_schema": {
            "expression_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.u128_expression.v1"
            ),
            "evaluation_order": "DEPTH_FIRST_LEFT_TO_RIGHT_CHECKED_UINT128",
            "unknown_or_extra_member_policy": "REJECT",
            "ordered_opcode_records": [
                {
                    "opcode_position": position,
                    "opcode": opcode,
                    "ordered_required_member_names_after_opcode": list(members),
                    "return_type": "U128",
                }
                for position, (opcode, members) in enumerate(expression_rows, 1)
            ],
        },
        "transfer_program_schema": {
            "ordered_member_names": ["program_version", "opcode"],
            "unknown_or_extra_member_policy": "REJECT",
            "ordered_transfer_opcode_records": [
                {
                    "opcode_position": position,
                    "opcode": opcode,
                    **contract,
                    "transfer_rule_id": rule_by_name[
                        _TRANSFER_RULE_NAME_BY_OPCODE[opcode]
                    ]["transfer_rule_id"],
                    "unknown_or_extra_member_policy": "REJECT",
                }
                for position, (opcode, contract) in enumerate(
                    _TRANSFER_OPCODE_CONTRACTS.items(), 1
                )
            ],
        },
        "meter_program_schema": {
            "ordered_member_names": [
                "program_version",
                "transition_attempt_count_expression",
                "logical_unbatched_transition_equivalent_count_expression",
                "batch_application_count_expression",
            ],
            "all_expressions_return": "U128",
            "event_expansion_order": [
                "LOGICAL_DESCRIPTOR_VISIT",
                "CACHE_INSERT",
                "TRANSITION_ATTEMPT",
                "BATCH_APPLICATION",
                "INTRINSIC_RULE_EVALUATION",
                "RESULT_CELL_EMIT",
                "STEP_COMMITMENT_EMIT",
                "RETENTION_OBSERVATION",
            ],
            "unknown_or_extra_member_policy": "REJECT",
        },
        "parameter_schema_record_schema": {
            "ordered_member_names": [
                "parameter_position",
                "parameter_name",
                "value_type",
                "nullable",
                "null_semantics",
                "authority_validation",
            ],
            "value_type_enum": [
                "BOOLEAN",
                "NONNEGATIVE_SAFE_INTEGER",
                "SIGNED_SAFE_INTEGER",
                "OPTIONAL_NONNEGATIVE_SAFE_INTEGER",
                "TEXT",
                "OPTIONAL_TEXT",
                "JSON_VALUE",
                "ORDERED_JSON_ARRAY",
                "TYPED_PATH",
            ],
        },
    }


def _parameter_schema_record(position: int, name: str) -> dict[str, Any]:
    boolean_names = {"boolean_literal"}
    integer_names = {
        "fixed_canonical_octets",
        "canonical_octets",
        "minimum_items",
        "maximum_items",
        "item_step_position",
        "child_step_position",
        "record_member_count",
        "record_syntax_octets_excluding_child_values",
        "text_language_position",
        "minimum_canonical_octets",
        "maximum_canonical_octets",
    }
    optional_integer_names = {
        "minimum_utf8_octets",
        "maximum_utf8_octets",
        "minimum_decoded_octets",
        "maximum_decoded_octets",
    }
    signed_integer_names = {"integer_minimum", "integer_maximum"}
    text_names = {
        "text_language_id",
        "language_kind",
        "built_in_language_kind",
        "item_value_schema_id",
        "referenced_type_name",
        "owner_type_name",
        "safe_relaxation_rule_id",
        "local_shutdown_analytic_catalog_id",
    }
    optional_text_names = {
        "built_in_language_kind",
        "ascii_dfa_id",
        "unicode_identifier_profile_id",
        "decimal_maximum",
        "owner_type_name",
    }
    array_names = {
        "ordered_probe_values",
        "ordered_literals",
        "ordered_run_records",
        "ordered_member_records",
        "ordered_alternative_records",
        "ordered_codec_coordinate_records",
        "fixed_authority_bindings",
        "ordered_application_invocation_records",
    }
    path_names = {"owner_typed_member_path", "authority_predicate_locator"}
    json_names = {
        "case_binding",
        "local_shutdown_analytic_catalog",
        "observer_closure_record",
    }
    memberships = [
        (name in boolean_names, "BOOLEAN", True),
        (name in integer_names, "NONNEGATIVE_SAFE_INTEGER", False),
        (name in signed_integer_names, "SIGNED_SAFE_INTEGER", False),
        (name in optional_integer_names, "OPTIONAL_NONNEGATIVE_SAFE_INTEGER", True),
        (name in text_names - optional_text_names, "TEXT", False),
        (name in optional_text_names, "OPTIONAL_TEXT", True),
        (name in array_names, "ORDERED_JSON_ARRAY", False),
        (name in path_names, "TYPED_PATH", False),
        (name in json_names, "JSON_VALUE", False),
    ]
    matches = [
        (value_type, nullable)
        for present, value_type, nullable in memberships
        if present
    ]
    _require(len(matches) == 1, f"parameter schema is absent or ambiguous: {name}")
    value_type, nullable = matches[0]
    return {
        "parameter_position": position,
        "parameter_name": name,
        "value_type": value_type,
        "nullable": nullable,
        "null_semantics": {
            "boolean_literal": "FULL_BOOLEAN_DOMAIN_SENTINEL",
            "owner_type_name": "NO_OWNER_CODEC_COORDINATE",
        }.get(name),
        "authority_validation": "RECOMPUTE_FROM_PINNED_LOCATOR_OR_EXACT_CHILD_REFERENCE",
    }


def _u128_const(value: int) -> dict[str, Any]:
    return {"opcode": "CONST_U128", "value": value}


def _u128_param(name: str) -> dict[str, Any]:
    return {"opcode": "PARAM_U128", "parameter_name": name}


def _u128_list_count(name: str) -> dict[str, Any]:
    return {"opcode": "PARAM_LIST_COUNT", "parameter_name": name}


def _checked_add(*operands: dict[str, Any]) -> dict[str, Any]:
    return {"opcode": "CHECKED_ADD", "ordered_operands": list(operands)}


def _checked_mul(*operands: dict[str, Any]) -> dict[str, Any]:
    return {"opcode": "CHECKED_MUL", "ordered_operands": list(operands)}


def _kernel_program(kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    transfer_by_kind = {
        "FIXED_VALUE": "CELL_FIXED_OCTETS_V1",
        "EXACT_BOOLEAN": "CELL_BOOLEAN_LITERAL_V1",
        "SAFE_INTEGER_BAND": "CELL_SAFE_INTEGER_INTERVAL_V1",
        "TEXT_FINITE": "CELL_FINITE_TEXT_V1",
        "TEXT_BUILTIN_BOUNDED": "CELL_BOUNDED_TEXT_OCTETS_V1",
        "TEXT_BOUNDED_LANGUAGE": "CELL_RELAXED_JSON_STRING_V1",
        "DERIVED_IDENTITY_FIXED_WIDTH": "CELL_DERIVED_IDENTITY_V1",
        "NULLABLE_BRANCH": "CELL_NULLABLE_V1",
        "OBJECT_REFERENCE": "CELL_CHILD_BOUNDS_ALIAS_V1",
        "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": "CELL_ARRAY_BATCH_V1",
        "ARRAY_STREAM_FOLD": "CELL_ARRAY_STREAM_V1",
        "RECORD_MEMBER_FOLD": "CELL_RECORD_V1",
        "TAGGED_UNION_BRANCH": "CELL_UNION_V1",
        "CODEC_INTERSECTION": "CELL_CODEC_INTERSECTION_V1",
        "SAFE_RELAXATION": "CELL_SAFE_RELAXATION_V1",
        "SCOPE_ROOT": "CELL_SCOPE_ROOT_V1",
        "APPLICATION_SCHEDULE_COUNT": "CELL_APPLICATION_WRAPPER_V1",
        "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP": "CELL_LOCAL_SHUTDOWN_SWEEP_V2",
    }
    one = _u128_const(1)
    transition_by_kind = {
        "FIXED_VALUE": one,
        "EXACT_BOOLEAN": _checked_add(
            one,
            {
                "opcode": "INDICATOR_PARAM_IS_NULL",
                "parameter_name": "boolean_literal",
            },
        ),
        "SAFE_INTEGER_BAND": _u128_list_count("ordered_probe_values"),
        "TEXT_FINITE": _u128_list_count("ordered_literals"),
        "TEXT_BUILTIN_BOUNDED": one,
        "TEXT_BOUNDED_LANGUAGE": one,
        "DERIVED_IDENTITY_FIXED_WIDTH": one,
        "NULLABLE_BRANCH": _u128_const(3),
        "OBJECT_REFERENCE": one,
        "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": _checked_add(
            one,
            {"opcode": "INDICATOR_PARAM_NONZERO", "parameter_name": "maximum_items"},
        ),
        "ARRAY_STREAM_FOLD": _checked_add(one, _u128_param("maximum_items")),
        "RECORD_MEMBER_FOLD": _checked_add(one, _u128_param("record_member_count")),
        "TAGGED_UNION_BRANCH": _checked_add(
            one, _u128_list_count("ordered_alternative_records")
        ),
        "CODEC_INTERSECTION": _checked_add(
            one, _u128_list_count("ordered_codec_coordinate_records")
        ),
        "SAFE_RELAXATION": one,
        "SCOPE_ROOT": one,
        "APPLICATION_SCHEDULE_COUNT": _checked_add(
            one, _u128_list_count("ordered_application_invocation_records")
        ),
        "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP": _u128_const(11),
    }
    logical_multiplier = {"opcode": "STEP_LOGICAL_TRANSFER_MULTIPLICITY"}
    logical_by_kind = {
        name: _checked_mul(expression, logical_multiplier)
        for name, expression in transition_by_kind.items()
    }
    array_logical_expression = _checked_mul(
        _checked_add(one, _u128_param("maximum_items")), logical_multiplier
    )
    logical_by_kind["ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH"] = array_logical_expression
    logical_by_kind["ARRAY_STREAM_FOLD"] = array_logical_expression
    batch_by_kind = {name: _u128_const(0) for name in transition_by_kind}
    batch_by_kind["ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH"] = {
        "opcode": "INDICATOR_PARAM_NONZERO",
        "parameter_name": "maximum_items",
    }
    return (
        {
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.cell_transfer_program.v1"
            ),
            "opcode": transfer_by_kind[kind],
        },
        {
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.kernel_meter_program.v1"
            ),
            "transition_attempt_count_expression": transition_by_kind[kind],
            "logical_unbatched_transition_equivalent_count_expression": logical_by_kind[
                kind
            ],
            "batch_application_count_expression": batch_by_kind[kind],
        },
    )


def _evaluate_u128_expression(
    expression: dict[str, Any],
    *,
    parameters: dict[str, Any],
    logical_transfer_multiplicity: int,
) -> int:
    _require(type(expression) is dict, "u128 expression is not an object")
    opcode = expression.get("opcode")
    if opcode == "CONST_U128":
        _require(set(expression) == {"opcode", "value"}, "CONST_U128 differs")
        value = expression["value"]
    elif opcode == "STEP_LOGICAL_TRANSFER_MULTIPLICITY":
        _require(
            set(expression) == {"opcode"},
            "STEP_LOGICAL_TRANSFER_MULTIPLICITY differs",
        )
        value = logical_transfer_multiplicity
    elif opcode == "PARAM_U128":
        _require(set(expression) == {"opcode", "parameter_name"}, "PARAM_U128 differs")
        value = parameters[expression["parameter_name"]]
    elif opcode == "PARAM_LIST_COUNT":
        _require(
            set(expression) == {"opcode", "parameter_name"},
            "PARAM_LIST_COUNT differs",
        )
        items = parameters[expression["parameter_name"]]
        _require(type(items) is list, "PARAM_LIST_COUNT input is not an array")
        value = len(items)
    elif opcode == "INDICATOR_PARAM_NONZERO":
        _require(
            set(expression) == {"opcode", "parameter_name"},
            "INDICATOR_PARAM_NONZERO differs",
        )
        operand = parameters[expression["parameter_name"]]
        _require(type(operand) is int and operand >= 0, "indicator operand differs")
        value = int(operand > 0)
    elif opcode == "INDICATOR_PARAM_IS_NULL":
        _require(
            set(expression) == {"opcode", "parameter_name"},
            "INDICATOR_PARAM_IS_NULL differs",
        )
        parameter_name = expression["parameter_name"]
        _require(parameter_name in parameters, "null-indicator parameter is absent")
        value = int(parameters[parameter_name] is None)
    elif opcode in {"CHECKED_ADD", "CHECKED_MUL"}:
        _require(
            set(expression) == {"opcode", "ordered_operands"},
            f"{opcode} differs",
        )
        operands = [
            _evaluate_u128_expression(
                operand,
                parameters=parameters,
                logical_transfer_multiplicity=logical_transfer_multiplicity,
            )
            for operand in expression["ordered_operands"]
        ]
        value = 0 if opcode == "CHECKED_ADD" else 1
        for operand in operands:
            candidate = value + operand if opcode == "CHECKED_ADD" else value * operand
            _require(candidate <= UINT128_MAXIMUM, f"{opcode} overflows UInt128")
            value = candidate
    else:
        _fail(f"unknown u128 expression opcode: {opcode}")
    _require(
        type(value) is int and 0 <= value <= UINT128_MAXIMUM, "u128 result differs"
    )
    return value


def _recurrence_catalog(
    identity_records: list[dict[str, Any]],
    inventory: dict[str, Any],
    transfer_rule_catalog: dict[str, Any],
) -> dict[str, Any]:
    def tagged_subject_schema(
        *,
        version: str,
        version_member: str,
        common_members: list[str],
        ordinary_members: list[str],
        local_members: list[str],
    ) -> dict[str, Any]:
        ordered_members = [
            version_member,
            "subject_variant",
            *common_members,
            *ordinary_members,
            *local_members,
        ]
        common_required = [version_member, "subject_variant", *common_members]
        return {
            version_member: version,
            "ordered_member_names": ordered_members,
            "discriminant_member_name": "subject_variant",
            "variant_enum": ["ORDINARY_STEP", "LOCAL_CONTROLLER"],
            "ordered_variant_records": [
                {
                    "variant_position": 1,
                    "subject_variant": "ORDINARY_STEP",
                    "ordered_required_member_names": [
                        *common_required,
                        *ordinary_members,
                    ],
                    "ordered_null_member_names": local_members,
                },
                {
                    "variant_position": 2,
                    "subject_variant": "LOCAL_CONTROLLER",
                    "ordered_required_member_names": [
                        *common_required,
                        *local_members,
                    ],
                    "ordered_null_member_names": ordinary_members,
                },
            ],
            "canonical_member_order": "ORDERED_MEMBER_NAMES",
            "unknown_or_extra_member_policy": "REJECT",
        }

    empty_signature = _state_signature(identity_records, position=1, components=[])
    array_signature = _state_signature(
        identity_records,
        position=2,
        components=[
            {
                "component_position": 1,
                "component_kind": "ITEM_COUNT",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
            {
                "component_position": 2,
                "component_kind": "CAPPED_ITEM_UPPER_OCTET_SUM",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
            {
                "component_position": 3,
                "component_kind": "COMMA_COUNT",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
        ],
    )
    stream_signature = _state_signature(
        identity_records,
        position=3,
        components=[
            {
                "component_position": 1,
                "component_kind": "ARRAY_ORDINAL",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
            {
                "component_position": 2,
                "component_kind": "ITEM_COUNT",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
            {
                "component_position": 3,
                "component_kind": "CAPPED_ITEM_UPPER_OCTET_SUM",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
            {
                "component_position": 4,
                "component_kind": "COMMA_COUNT",
                "value_type": "NONNEGATIVE_SAFE_INTEGER",
                "nullable": False,
                "value_source_kind": "DERIVED_FOLD_STATE",
                "value_source_locator": None,
            },
        ],
    )
    local_signature = _state_signature(
        identity_records,
        position=4,
        components=[
            {
                "component_position": position,
                "component_kind": kind,
                "value_type": value_type,
                "nullable": nullable,
                "value_source_kind": "DERIVED_LOCAL_SWEEP_STATE",
                "value_source_locator": (
                    "/recurrence_catalog/local_shutdown_analytic_catalog/"
                    "ordered_controller_state_records/*/ordered_state_components/"
                    f"{position - 1}"
                ),
            }
            for position, (kind, value_type, nullable) in enumerate(
                (
                    (
                        "PROCESSED_MUTABLE_LIMIT_COUNT",
                        "NONNEGATIVE_SAFE_INTEGER",
                        False,
                    ),
                    ("CURRENT_CANDIDATE_OUTCOME", "TEXT_ENUM", False),
                    (
                        "CURRENT_DECISIVE_MUTATED_VALUE",
                        "NONNEGATIVE_SAFE_INTEGER",
                        True,
                    ),
                    (
                        "CURRENT_DECISIVE_ATTAINABLE_MAXIMUM_OCTETS",
                        "NONNEGATIVE_SAFE_INTEGER",
                        True,
                    ),
                    (
                        "BEST_CANDIDATE_LEXICAL_POSITION",
                        "NONNEGATIVE_SAFE_INTEGER",
                        True,
                    ),
                    (
                        "BEST_CANDIDATE_MUTATED_VALUE",
                        "NONNEGATIVE_SAFE_INTEGER",
                        True,
                    ),
                    (
                        "BEST_CANDIDATE_ABSOLUTE_DELTA",
                        "NONNEGATIVE_SAFE_INTEGER",
                        True,
                    ),
                    (
                        "BEST_CANDIDATE_ATTAINABLE_MAXIMUM_OCTETS",
                        "NONNEGATIVE_SAFE_INTEGER",
                        True,
                    ),
                ),
                1,
            )
        ],
    )
    relaxation_rows = (
        (
            "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1",
            "INTRINSIC_CROSS_OR_APPLICATION_PREDICATE",
            "SCHEMA_CANONICALIZATION_CODEC_AND_FIXED_BINDINGS",
            "DELETE_CONJUNCT_PRODUCES_SUPERSET",
        ),
        (
            "DROP_ARRAY_ORDER_AND_UNIQUENESS_TO_SEQUENCE_SUPERSET_V1",
            "ARRAY_ORDER_AND_UNIQUENESS_PREDICATE",
            "ARRAY_ITEM_SCHEMA_AND_CARDINALITY",
            "REMOVE_RELATION_PRODUCES_SEQUENCE_SUPERSET",
        ),
        (
            "DERIVED_IDENTITY_FIXED_WIDTH_PAYLOAD_SUPERSET_V1",
            "PAYLOAD_TO_IDENTITY_EQUALITY",
            "PAYLOAD_SCHEMA_AND_64_HEX_ID_WIDTH",
            "REMOVE_EQUALITY_KEEP_FIXED_WIDTH_DOMAIN",
        ),
        (
            "DROP_COMPLETE_TEXT_LANGUAGE_TO_JSON_STRING_SUPERSET_V1",
            "TEXT_LANGUAGE_PREDICATE",
            "JSON_STRING_CANONICALIZATION_AND_CODEC_BOUND",
            "REMOVE_LANGUAGE_PREDICATE_PRODUCES_JSON_STRING_SUPERSET",
        ),
    )
    relaxations = []
    for position, (name, deleted, retained, soundness) in enumerate(relaxation_rows, 1):
        payload = {
            "relaxation_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.safe_relaxation_rule.v2"
            ),
            "relaxation_name": name,
            "deleted_predicate_class": deleted,
            "retained_semantics": retained,
            "soundness_rule": soundness,
        }
        relaxations.append(
            {
                "relaxation_position": position,
                **payload,
                "safe_relaxation_rule_id": _semantic_id(
                    _identity_domain(identity_records, "SAFE_RELAXATION_RULE"), payload
                ),
            }
        )
    batch_payload = {
        "batch_equivalence_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.homogeneous_run_batch_equivalence.v1"
        ),
        "state_signature_id": array_signature["state_signature_id"],
        "identity_state_components": [0, 0, 0],
        "ordered_closed_form_update_records": [
            {
                "update_position": 1,
                "component": "ITEM_COUNT",
                "update_opcode": "CHECKED_ADD_COMPONENTS_V1",
                "ordered_operand_components": ["LEFT.ITEM_COUNT", "RIGHT.ITEM_COUNT"],
            },
            {
                "update_position": 2,
                "component": "CAPPED_ITEM_UPPER_OCTET_SUM",
                "update_opcode": "CAPPED_ADD_COMPONENTS_TO_EFFECTIVE_CEILING_V1",
                "ordered_operand_components": [
                    "LEFT.CAPPED_ITEM_UPPER_OCTET_SUM",
                    "RIGHT.CAPPED_ITEM_UPPER_OCTET_SUM",
                ],
            },
            {
                "update_position": 3,
                "component": "COMMA_COUNT",
                "update_opcode": "CHECKED_ADD_COMMA_BOUNDARY_V1",
                "ordered_operand_components": [
                    "LEFT.COMMA_COUNT",
                    "RIGHT.COMMA_COUNT",
                    "INDICATOR_LEFT_AND_RIGHT_NONEMPTY",
                ],
            },
        ],
        "closed_form_power_record": {
            "power_opcode": "HOMOGENEOUS_ARRAY_RUN_POWER_V1",
            "ordered_output_components": [
                "ITEM_COUNT=N",
                "CAPPED_ITEM_UPPER_OCTET_SUM=CAPPED_MUL(N,ITEM_UPPER)",
                "COMMA_COUNT=MAX(N-1,0)",
            ],
        },
        "ordered_absent_observer_kinds": [
            "ORDINAL",
            "ORDER",
            "UNIQUENESS",
            "STATEFUL_RULE",
            "IDENTITY_RELATION",
        ],
        "surviving_canonical_boundary_component": "COMMA_COUNT",
        "small_exhaustive_maximum_cardinality": 16,
        "inductive_law": {
            "law_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "homogeneous_run_inductive_law.v1"
            ),
            "base_cardinality": 0,
            "base_state_components": [0, 0, 0],
            "step_opcode": "MERGE_LEFT_RUN_WITH_ONE_ITEM_RIGHT_RUN_V1",
            "claimed_equivalence": "CLOSED_FORM_POWER_EQUALS_INCREASING_UNBATCHED_FOLD",
        },
    }
    batch = {
        **batch_payload,
        "batch_equivalence_id": _semantic_id(
            _identity_domain(identity_records, "HOMOGENEOUS_RUN_BATCH_EQUIVALENCE"),
            batch_payload,
        ),
    }
    kernels_raw = (
        ("FIXED_VALUE", "FIXED_VALUE_PARAMETERS_V1", ("fixed_canonical_octets",), 1),
        ("EXACT_BOOLEAN", "EXACT_BOOLEAN_PARAMETERS_V1", ("boolean_literal",), 1),
        (
            "SAFE_INTEGER_BAND",
            "SAFE_INTEGER_PARAMETERS_V1",
            ("integer_minimum", "integer_maximum", "ordered_probe_values"),
            1,
        ),
        (
            "TEXT_FINITE",
            "TEXT_FINITE_PARAMETERS_V1",
            ("text_language_position", "text_language_id", "ordered_literals"),
            1,
        ),
        (
            "TEXT_BUILTIN_BOUNDED",
            "TEXT_BUILTIN_BOUNDED_PARAMETERS_V1",
            (
                "built_in_language_kind",
                "minimum_canonical_octets",
                "maximum_canonical_octets",
                "text_language_id",
                "text_language_position",
            ),
            1,
        ),
        (
            "TEXT_BOUNDED_LANGUAGE",
            "TEXT_BOUNDED_LANGUAGE_PARAMETERS_V1",
            (
                "text_language_position",
                "text_language_id",
                "language_kind",
                "built_in_language_kind",
                "ascii_dfa_id",
                "unicode_identifier_profile_id",
                "minimum_utf8_octets",
                "maximum_utf8_octets",
                "minimum_decoded_octets",
                "maximum_decoded_octets",
                "decimal_maximum",
            ),
            1,
        ),
        (
            "DERIVED_IDENTITY_FIXED_WIDTH",
            "IDENTITY_WIDTH_PARAMETERS_V1",
            ("canonical_octets",),
            1,
        ),
        ("NULLABLE_BRANCH", "NULLABLE_PARAMETERS_V1", ("child_step_position",), 1),
        (
            "OBJECT_REFERENCE",
            "OBJECT_REFERENCE_PARAMETERS_V1",
            ("referenced_type_name", "child_step_position"),
            1,
        ),
        (
            "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH",
            "ARRAY_RUN_PARAMETERS_V1",
            (
                "minimum_items",
                "maximum_items",
                "item_value_schema_id",
                "item_step_position",
                "ordered_run_records",
                "observer_closure_record",
            ),
            2,
        ),
        (
            "ARRAY_STREAM_FOLD",
            "ARRAY_STREAM_PARAMETERS_V1",
            ("minimum_items", "maximum_items", "item_step_position"),
            3,
        ),
        (
            "RECORD_MEMBER_FOLD",
            "RECORD_PARAMETERS_V1",
            (
                "record_member_count",
                "ordered_member_records",
                "record_syntax_octets_excluding_child_values",
            ),
            1,
        ),
        (
            "TAGGED_UNION_BRANCH",
            "UNION_PARAMETERS_V1",
            (
                "ordered_alternative_records",
                "owner_type_name",
                "owner_typed_member_path",
            ),
            1,
        ),
        (
            "CODEC_INTERSECTION",
            "CODEC_PARAMETERS_V1",
            ("ordered_codec_coordinate_records", "child_step_position"),
            1,
        ),
        (
            "SAFE_RELAXATION",
            "RELAXATION_PARAMETERS_V1",
            (
                "safe_relaxation_rule_id",
                "authority_predicate_locator",
                "child_step_position",
            ),
            1,
        ),
        (
            "SCOPE_ROOT",
            "SCOPE_ROOT_PARAMETERS_V1",
            ("case_binding", "fixed_authority_bindings", "child_step_position"),
            1,
        ),
        (
            "APPLICATION_SCHEDULE_COUNT",
            "APPLICATION_SCHEDULE_PARAMETERS_V1",
            ("ordered_application_invocation_records", "child_step_position"),
            1,
        ),
        (
            "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP",
            "LOCAL_SHUTDOWN_ANALYTIC_PARAMETERS_V1",
            ("local_shutdown_analytic_catalog_id",),
            4,
        ),
    )
    signatures = {
        1: empty_signature,
        2: array_signature,
        3: stream_signature,
        4: local_signature,
    }
    kernels = []
    for position, (
        kind,
        variant,
        members,
        signature_position,
    ) in enumerate(kernels_raw, 1):
        transfer_program, meter_program = _kernel_program(kind)
        record = {
            "kernel_position": position,
            "derivation_kind": kind,
            "parameter_variant": variant,
            "ordered_parameter_member_names": list(members),
            "ordered_parameter_schema_records": [
                _parameter_schema_record(member_position, member_name)
                for member_position, member_name in enumerate(members, 1)
            ],
            "state_signature_id": signatures[signature_position]["state_signature_id"],
            "transfer_order": "CATALOG_ORDER_CAP_FIRST_CHECKED_UINT128",
            "merge_rule": "FULL_CACHE_KEY_BYTE_EQUAL_MAX_UPPER_BOUND",
            "transfer_program": transfer_program,
            "meter_program": meter_program,
        }
        kernels.append(
            {**record, "kernel_record_sha256": _sha256(_canonical_bytes(record))}
        )
    payload = {
        "recurrence_catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.recurrence_catalog.v3"
        ),
        "arithmetic_policy": {
            "integer_kind": "CHECKED_UINT128",
            "published_maximum": SAFE_INTEGER_MAXIMUM,
            "cap_order": "CHECK_PROSPECTIVE_THEN_COMMIT_THEN_MATERIALIZE",
            "ordered_arithmetic_opcode_records": [
                {
                    "opcode_position": 1,
                    "opcode": "CHECKED_ADD_U128_V1",
                    "overflow_policy": "REJECT_BEFORE_COMMIT",
                },
                {
                    "opcode_position": 2,
                    "opcode": "CHECKED_SUB_U128_V1",
                    "underflow_policy": "REJECT_BEFORE_COMMIT",
                },
                {
                    "opcode_position": 3,
                    "opcode": "CHECKED_MUL_U128_V1",
                    "overflow_policy": "REJECT_BEFORE_COMMIT",
                },
                {
                    "opcode_position": 4,
                    "opcode": "CAPPED_ADD_U128_TO_CEILING_V1",
                    "overflow_policy": "SATURATE_WITH_EXCEEDED_CEILING_TRUE",
                },
                {
                    "opcode_position": 5,
                    "opcode": "CAPPED_MUL_U128_TO_CEILING_V1",
                    "overflow_policy": "SATURATE_WITH_EXCEEDED_CEILING_TRUE",
                },
                {
                    "opcode_position": 6,
                    "opcode": "MIN_U128_V1",
                    "empty_operand_policy": "REJECT",
                },
            ],
        },
        "cell_invariant": {
            "cell_members": [
                "cell_status",
                "certified_lower_bound_octets",
                "certified_upper_bound_octets",
                "ordered_state_components",
            ],
            "status_enum": ["MAY_BE_NONEMPTY", "PROVABLY_EMPTY"],
            "invariant": "for_all_v_in_relaxed_domain:LB<=CJ_LEN(v)<=U<=B",
            "intermediate_attainability_claimed": False,
        },
        "instruction_set": _instruction_set(transfer_rule_catalog),
        "transfer_rule_catalog": transfer_rule_catalog,
        "ordered_state_signature_records": [
            empty_signature,
            array_signature,
            stream_signature,
            local_signature,
        ],
        "cache_key_schema": tagged_subject_schema(
            version=(
                "riskyieldmm.raw_v8_step2_external_schema_v2.recurrence_cache_key.v3"
            ),
            version_member="cache_key_version",
            common_members=[
                "logical_count_plan_id",
                "effective_canonical_octet_ceiling",
                "state_signature_id",
                "ordered_state_components",
            ],
            ordinary_members=[
                "logical_derivation_step_position",
                "derivation_kind",
                "occurrence_ordinal",
                "array_ordinal",
                "owner_profile_position",
                "application_invocation_ordinal",
                "observation_ordinal",
            ],
            local_members=[
                "local_controller_state_position",
                "local_controller_state_id",
            ],
        )
        | {
            "equality_authority": "FULL_COMPACT_CANONICAL_BYTES",
            "lifetime": "ONE_CASE_RELEASE_AFTER_LAST_PARENT_COMMITMENT",
        },
        "transition_token_schema": tagged_subject_schema(
            version=(
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "recurrence_transition_token.v3"
            ),
            version_member="transition_token_version",
            common_members=[
                "logical_count_plan_id",
                "transition_ordinal",
                "transition_kind",
                "source_state_components",
                "input_symbol",
                "candidate_state_components",
                "candidate_certified_upper_bound_octets",
            ],
            ordinary_members=["logical_derivation_step_position"],
            local_members=[
                "local_controller_transition_position",
                "local_controller_transition_id",
                "source_controller_state_id",
                "target_controller_state_id",
            ],
        ),
        "result_cell_schema": tagged_subject_schema(
            version=(
                "riskyieldmm.raw_v8_step2_external_schema_v2.recurrence_result_cell.v3"
            ),
            version_member="result_cell_version",
            common_members=[
                "logical_count_plan_id",
                "state_signature_id",
                "ordered_state_components",
                "cell_status",
                "certified_lower_bound_octets",
                "certified_upper_bound_octets",
            ],
            ordinary_members=[
                "logical_derivation_step_position",
                "result_cell_ordinal",
            ],
            local_members=[
                "local_controller_state_position",
                "local_controller_state_id",
            ],
        ),
        "step_commitment_schema": tagged_subject_schema(
            version=(
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "recurrence_step_commitment.v3"
            ),
            version_member="step_commitment_version",
            common_members=[
                "logical_count_plan_id",
                "state_count",
                "certified_upper_bound_octets",
                "ordered_result_cell_sha256",
            ],
            ordinary_members=["logical_derivation_step_position"],
            local_members=[
                "local_shutdown_analytic_catalog_id",
                "initial_controller_state_id",
                "terminal_controller_state_id",
            ],
        ),
        "ordered_safe_relaxation_records": relaxations,
        "homogeneous_run_batch_equivalence": batch,
        "ordered_derivation_kernel_records": kernels,
        "local_shutdown_analytic_catalog": _local_shutdown_catalog(
            identity_records,
            inventory,
            state_signature_id=local_signature["state_signature_id"],
            derivation_kernel_record_sha256=next(
                row["kernel_record_sha256"]
                for row in kernels
                if row["derivation_kind"] == "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP"
            ),
        ),
    }
    return {
        **payload,
        "recurrence_catalog_id": _semantic_id(
            _identity_domain(identity_records, "RECURRENCE_CATALOG"), payload
        ),
    }


def _legacy_event_catalog(identity_records: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = (
        (
            "CASE_OPEN",
            "BEFORE_FIRST_PLAN_STEP",
            ((1, "ADD", "ONE"),),
        ),
        (
            "LOGICAL_DESCRIPTOR_VISIT",
            "BEFORE_DESCRIPTOR_TRANSFER",
            ((2, "ADD", "LOGICAL_MULTIPLICITY"),),
        ),
        (
            "CACHE_INSERT",
            "AFTER_KEY_BYTES_FROZEN_BEFORE_INSERT",
            (
                (7, "ADD", "ONE"),
                (8, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            ),
        ),
        (
            "TRANSITION_ATTEMPT",
            "AFTER_TOKEN_BYTES_FROZEN_BEFORE_GUARD_OR_DEDUP",
            (
                (4, "ADD", "ONE"),
                (5, "ADD", "LOGICAL_MULTIPLICITY"),
                (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            ),
        ),
        (
            "BATCH_APPLICATION",
            "BEFORE_NONEMPTY_CLOSED_FORM_RUN_UPDATE",
            ((6, "ADD", "ONE"),),
        ),
        (
            "RESULT_CELL_EMIT",
            "AFTER_CELL_BYTES_FROZEN_BEFORE_KEY_MERGE",
            (
                (3, "ADD", "ONE"),
                (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (18, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            ),
        ),
        (
            "STEP_COMMITMENT_EMIT",
            "AFTER_COMMITMENT_BYTES_FROZEN",
            (
                (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (18, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            ),
        ),
        (
            "FINAL_RESULT_EMIT",
            "AFTER_RESULT_BYTES_FROZEN",
            (
                (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (18, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            ),
        ),
        (
            "INTRINSIC_RULE_EVALUATION",
            "BEFORE_COMPLETE_INTRINSIC_RULE_ROOT",
            ((12, "ADD", "ONE"),),
        ),
        (
            "CROSS_RULE_EVALUATION",
            "BEFORE_COMPLETE_CROSS_RULE_ROOT",
            ((13, "ADD", "ONE"),),
        ),
        (
            "APPLICATION_EVALUATION",
            "BEFORE_COMPLETE_APPLICATION_INVOCATION",
            ((14, "ADD", "ONE"),),
        ),
        (
            "HASH_PREIMAGE",
            "AFTER_PREIMAGE_FROZEN_BEFORE_DIGEST_PUBLICATION",
            ((11, "ADD", "SUBJECT_CANONICAL_OCTETS"),),
        ),
        (
            "RETENTION_OBSERVATION",
            "AFTER_PROSPECTIVE_LIVE_SET_FROZEN_BEFORE_MATERIALIZATION",
            ((17, "MAX", "OBSERVED_VALUE"),),
        ),
        (
            "DERIVATION_DEPTH_OBSERVATION",
            "AFTER_TEMPLATE_DEPENDENCY_DEPTH_DERIVATION",
            ((15, "MAX", "OBSERVED_VALUE"),),
        ),
        (
            "ITERATION_DEPTH_OBSERVATION",
            "AFTER_LOGICAL_VALIDATION_DEPTH_DERIVATION",
            ((16, "MAX", "OBSERVED_VALUE"),),
        ),
        (
            "EVENT_STREAM_CLOSE",
            "AFTER_ALL_PRIOR_EVENT_TOKENS_BEFORE_STREAM_HASH",
            (
                (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
                (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            ),
        ),
    )
    payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_event_catalog.v1"
        ),
        "event_schema": {
            "version": "riskyieldmm.raw_v8_step2_external_schema_v2.logical_meter_event_token.v2",
            "ordered_member_names": [
                "event_position",
                "logical_derivation_step_position",
                "event_kind",
                "event_ordinal",
                "subject_kind",
                "subject_ordinal",
                "subject_canonical_octets",
                "logical_multiplicity",
                "observed_value",
            ],
            "nullable_member_names": [
                "logical_derivation_step_position",
                "subject_ordinal",
                "observed_value",
            ],
            "digest_preimage_excludes_metric_values": True,
        },
        "metric_update_schema": {
            "ordered_member_names": [
                "metric_position",
                "update_kind",
                "value_source",
            ],
            "update_kind_enum": ["ADD", "MAX"],
            "value_source_enum": [
                "ONE",
                "SUBJECT_CANONICAL_OCTETS",
                "LOGICAL_MULTIPLICITY",
                "OBSERVED_VALUE",
            ],
            "application_rule": (
                "resolve_value_source_then_cap_check_then_commit_in_metric_position_order"
            ),
        },
        "ordered_event_kind_records": [
            {
                "event_kind_position": pos,
                "event_kind": kind,
                "emission_order": order,
                "ordered_metric_update_program": [
                    {
                        "metric_position": metric_position,
                        "update_kind": update_kind,
                        "value_source": value_source,
                    }
                    for metric_position, update_kind, value_source in updates
                ],
            }
            for pos, (kind, order, updates) in enumerate(kinds, 1)
        ],
        "event_stream_close_rule": {
            "stream_preimage_members": [
                "logical_event_stream_version",
                "logical_count_plan_id",
                "ordered_pre_close_logical_event_tokens",
            ],
            "event_stream_close_token_is_included_in_preimage": False,
            "hash_preimage_token_is_included_in_preimage": False,
            "hash_preimage_event_follows_event_stream_close": True,
            "hash_preimage_subject_is_complete_stream_preimage": True,
            "no_event_follows_stream_hash": True,
            "comparator_recomputes_both_excluded_control_events": True,
        },
    }
    return {
        **payload,
        "logical_event_catalog_id": _semantic_id(
            _identity_domain(identity_records, "LOGICAL_EVENT_CATALOG"), payload
        ),
    }


def _validated_case_event_grammar(raw: bytes) -> dict[str, Any]:
    _require(
        b"CHALLENGER" not in raw.upper(), "event grammar retains challenger placeholder"
    )
    value = _parse_strict_canonical_json(
        raw, label="case-level event grammar", root_kind="OBJECT"
    )
    _require(type(value) is dict, "case-level event grammar root is not an object")
    ordered_members = [
        "grammar_version",
        "unknown_or_extra_member_policy",
        "global_event_position_rule",
        "event_ordinal_rule",
        "event_expression_instruction_set",
        "event_metadata_program",
        "ordered_execution_phase_records",
        "ordered_subject_schema_records",
        "ordered_case_program_records",
        "transition_expansion_contract",
        "ordered_case_hash_program_records",
        "byte_metric_partition",
        "live_set_program",
        "stream_finalization_program",
        "final_result_subject_contract",
        "full_case_execution_program",
        "hand_oracle_contract",
        "ordered_hand_oracle_records",
    ]
    _require(
        set(value) == set(ordered_members), "case-level event grammar members differ"
    )
    _require(
        value["unknown_or_extra_member_policy"] == "REJECT",
        "case-level event grammar is not fail-closed",
    )
    _require(
        value["ordered_hand_oracle_records"] == [],
        "source grammar must not carry generator-owned oracle rows",
    )
    metadata = value["event_metadata_program"]
    _require(
        set(metadata)
        == {
            "binding_rule",
            "logical_derivation_step_position_source_enum",
            "observed_value_source_enum",
            "ordered_program_metadata_records",
            "program_version",
            "subject_ordinal_source_enum",
            "unknown_or_extra_member_policy",
        },
        "event metadata program members differ",
    )
    _require(
        metadata["program_version"]
        == ("riskyieldmm.raw_v8_step2_external_schema_v2.event_metadata_program.v1")
        and metadata["unknown_or_extra_member_policy"] == "REJECT"
        and metadata["binding_rule"]
        == (
            "ZIP_PROGRAM_POSITION_THEN_EMISSION_POSITION_AND_MATERIALIZE_"
            "METADATA_ON_EMISSION_RECORD_BEFORE_TOKENIZATION_V1"
        )
        and metadata["logical_derivation_step_position_source_enum"]
        == ["NULL", "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"]
        and metadata["observed_value_source_enum"] == ["NULL", "SUBJECT_OBSERVED_VALUE"]
        and metadata["subject_ordinal_source_enum"]
        == [
            "NULL",
            "EMISSION_SUBJECT_COLLECTION_ORDINAL",
            "EVENT_KIND_ORDINAL",
            "DERIVATION_UNIT_ORDINAL",
        ],
        "event metadata root policy differs",
    )
    programs = value["ordered_case_program_records"]
    metadata_rows = metadata["ordered_program_metadata_records"]
    _require(
        len(metadata_rows) == len(programs) == 9,
        "event metadata program count differs",
    )
    row_members = {
        "logical_derivation_step_position_source",
        "observed_value_sources",
        "ordered_subject_role_literals",
        "program_name",
        "program_position",
        "subject_ordinal_sources",
    }
    observed_event_kinds = {
        "RETENTION_OBSERVATION",
        "DERIVATION_DEPTH_OBSERVATION",
        "ITERATION_DEPTH_OBSERVATION",
    }
    for position, (program, row) in enumerate(
        zip(programs, metadata_rows, strict=True), 1
    ):
        emissions = program["ordered_event_emission_records"]
        _require(set(row) == row_members, "event metadata row members differ")
        _require(
            row["program_position"] == position == program["program_position"]
            and row["program_name"] == program["program_name"],
            "event metadata program binding differs",
        )
        _require(
            row["logical_derivation_step_position_source"]
            in metadata["logical_derivation_step_position_source_enum"]
            and (
                row["logical_derivation_step_position_source"]
                == "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"
            )
            == (program["program_name"] == "ORDINARY_POSTORDER_STEPS"),
            "event metadata derivation-step source differs",
        )
        role_literals = row["ordered_subject_role_literals"]
        ordinal_sources = row["subject_ordinal_sources"]
        observed_sources = row["observed_value_sources"]
        _require(
            len(role_literals)
            == len(ordinal_sources)
            == len(observed_sources)
            == len(emissions),
            "event metadata emission cardinality differs",
        )
        for emission, role, ordinal_source, observed_source in zip(
            emissions,
            role_literals,
            ordinal_sources,
            observed_sources,
            strict=True,
        ):
            _require(
                type(role) is str
                and bool(role)
                and role == role.upper()
                and ordinal_source in metadata["subject_ordinal_source_enum"]
                and observed_source in metadata["observed_value_source_enum"],
                "event metadata emission value differs",
            )
            _require(
                (observed_source == "SUBJECT_OBSERVED_VALUE")
                == (emission["event_kind"] in observed_event_kinds),
                "event observed-value source differs",
            )
    final_contract = value["final_result_subject_contract"]
    _require(
        final_contract["commitment_material_member_name"]
        == "ordered_step_commitment_digest_records"
        and "ordered_step_result_commitments"
        in final_contract["forbidden_member_names"],
        "final result does not bind digest-only commitment ownership",
    )
    return {name: value[name] for name in ordered_members}


def _validate_full_case_execution_program(
    grammar: dict[str, Any], recurrence: dict[str, Any]
) -> None:
    program = grammar["full_case_execution_program"]
    _require(
        set(program)
        == {
            "program_version",
            "unknown_or_extra_member_policy",
            "ambient_ceiling_source",
            "ordinary_derivation_unit_order",
            "local_derivation_unit_order",
            "derivation_unit_context_program",
            "ordinary_cell_execution_program",
            "ordinary_transition_input_symbol_contract",
            "local_transition_expansion_program",
            "local_controller_state_cell_program",
            "ordered_kernel_transition_expansion_program_records",
            "ordered_subject_constructor_records",
            "ordinary_event_cardinality_program",
            "local_event_cardinality_program",
            "rule_application_event_program",
            "depth_observation_program",
            "retention_observation_program",
            "final_result_program",
            "stream_finalization_program",
            "subject_collection_export_name",
        },
        "full-case execution program members differ",
    )
    _require(
        program["program_version"]
        == (
            "riskyieldmm.raw_v8_step2_external_schema_v2.full_case_execution_program.v1"
        )
        and program["unknown_or_extra_member_policy"] == "REJECT"
        and program["ambient_ceiling_source"]
        == "/recurrence_catalog/arithmetic_policy/published_maximum"
        and program["ordinary_derivation_unit_order"]
        == "TEMPLATE_STEP_POSITION_ASCENDING_STRICT_POSTORDER_V1"
        and program["local_derivation_unit_order"]
        == "ONE_CONTROLLER_UNIT_STATES_1_TO_12_TRANSITIONS_1_TO_11_V1",
        "full-case execution root policy differs",
    )
    _require(
        program["derivation_unit_context_program"]
        == {
            "local_unit": {
                "derivation_kind": "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
                "effective_canonical_octet_ceiling_source": "AMBIENT_CEILING",
                "logical_derivation_step_id_source": "PLAN.local_analytic_catalog_id",
                "logical_derivation_step_position": None,
                "ordered_result_cell_source": (
                    "LOCAL_CONTROLLER_STATE_CELLS_IN_POSITION_ORDER"
                ),
                "owner_profile_position": None,
                "state_signature_source": "LOCAL_CATALOG.state_signature_id",
                "subject_variant": "LOCAL_CONTROLLER",
            },
            "ordinary_unit": {
                "derivation_kind_source": "STEP.derivation_kind",
                "effective_canonical_octet_ceiling_source": "AMBIENT_CEILING",
                "logical_derivation_step_id_source": (
                    "STEP.logical_derivation_step_id"
                ),
                "logical_derivation_step_position_source": (
                    "STEP.template_step_position"
                ),
                "ordered_result_cell_source": "SINGLE_EVALUATED_STEP_RESULT_CELL",
                "owner_profile_position_source": (
                    "MATCH_PROFILE_PROGRAM_ID_TO_PROFILE_POSITION_OR_NULL"
                ),
                "state_signature_source": "STEP.state_signature_id",
                "subject_variant": "ORDINARY_STEP",
            },
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "derivation_unit_context_program.v1"
            ),
            "unknown_or_extra_member_policy": "REJECT",
        },
        "derivation-unit context program differs",
    )
    _require(
        program["ordinary_cell_execution_program"]
        == {
            "ambient_ceiling_source": (
                "/recurrence_catalog/arithmetic_policy/published_maximum"
            ),
            "cell_transfer_rule_source": (
                "KERNEL.transfer_program.opcode_TO_INSTRUCTION_SET.transfer_rule_id"
            ),
            "child_cell_order": "STEP.ordered_child_step_positions",
            "execution_opcode": "EXECUTE_LINKED_LOW_LEVEL_TRANSFER_RULE_AST_V1",
            "profile_root_conditioning_source": (
                "BOUND_PROFILE_CONDITIONING_PROGRAM_P2_AT_ROOT_ONLY"
            ),
            "result_cell_count_per_step": 1,
            "step_order": "TEMPLATE_STEP_POSITION_ASCENDING_STRICT_POSTORDER_V1",
        },
        "ordinary cell execution program differs",
    )
    _require(
        program["ordinary_transition_input_symbol_contract"]
        == {
            "ordered_member_names": [
                "derivation_kind",
                "physical_transition_ordinal",
            ],
            "unknown_or_extra_member_policy": "REJECT",
        },
        "ordinary transition input-symbol contract differs",
    )
    _require(
        program["local_transition_expansion_program"]
        == {
            "candidate_state_component_source": (
                "CONTROLLER_TRANSITION.expected_target_state_components"
            ),
            "candidate_upper_bound_source": (
                "TARGET_STATE_CELL.certified_upper_bound_octets"
            ),
            "input_symbol_source": (
                "CONTROLLER_TRANSITION.input_mutable_limit_lexical_position"
            ),
            "logical_unbatched_count_per_token": 1,
            "physical_transition_ordinal_source": (
                "CONTROLLER_TRANSITION.controller_transition_position"
            ),
            "physical_transition_count_source": (
                "LOCAL_CATALOG.fixed_controller_transition_count"
            ),
            "source_state_selector": "CONTROLLER_STATE_AT_TRANSITION_POSITION",
            "source_state_component_source": ("SOURCE_STATE.ordered_state_components"),
            "target_state_cell_selector": (
                "RESULT_CELL_AT_TRANSITION_POSITION_PLUS_ONE"
            ),
            "transition_order": (
                "controller_transition_position_ASCENDING_CONTIGUOUS_ONE_BASED"
            ),
        },
        "local transition expansion program differs",
    )
    _require(
        program["local_controller_state_cell_program"]
        == {
            "ambient_ceiling_source": (
                "/recurrence_catalog/arithmetic_policy/published_maximum"
            ),
            "cell_status": "MAY_BE_NONEMPTY",
            "certified_lower_bound_octets": 0,
            "certified_upper_bound_rule": (
                "INITIAL_BASELINE_INTERMEDIATE_COMPONENT_3_TERMINAL_COMPONENT_7_V1"
            ),
            "initial_controller_state_source": (
                "CONTROLLER_STATE_AT_LOCAL_CATALOG_INITIAL_POSITION"
            ),
            "result_cell_order": (
                "controller_state_position_ASCENDING_CONTIGUOUS_ONE_BASED"
            ),
            "root_result_cell_source": "TERMINAL_CONTROLLER_STATE_CELL",
            "state_component_source": ("CONTROLLER_STATE.ordered_state_components"),
            "state_signature_source": "CONTROLLER_STATE.state_signature_id",
            "terminal_controller_state_source": (
                "CONTROLLER_STATE_AT_LOCAL_CATALOG_TERMINAL_POSITION"
            ),
        },
        "local controller state-cell program differs",
    )

    kernels = recurrence["ordered_derivation_kernel_records"]
    expansions = program["ordered_kernel_transition_expansion_program_records"]
    _require(
        len(expansions) == len(kernels) == 18, "transition expansion count differs"
    )
    expansion_members = {
        "kernel_position",
        "derivation_kind",
        "kernel_record_sha256",
        "program_version",
        "physical_transition_count_expression_pointer",
        "logical_unbatched_count_expression_pointer",
        "token_ordinal_rule",
        "logical_count_distribution_rule",
        "source_state_component_rule",
        "input_symbol_rule",
        "candidate_state_component_rule",
        "candidate_upper_bound_rule",
    }
    for position, (kernel, expansion) in enumerate(
        zip(kernels, expansions, strict=True), 1
    ):
        _require(
            set(expansion) == expansion_members, "transition expansion members differ"
        )
        _require(
            expansion["kernel_position"] == position
            and expansion["derivation_kind"] == kernel["derivation_kind"]
            and expansion["kernel_record_sha256"] == kernel["kernel_record_sha256"],
            "transition expansion kernel binding differs",
        )
        base = (
            "/recurrence_catalog/ordered_derivation_kernel_records/"
            f"{position - 1}/meter_program"
        )
        _require(
            expansion["physical_transition_count_expression_pointer"]
            == f"{base}/transition_attempt_count_expression"
            and expansion["logical_unbatched_count_expression_pointer"]
            == (f"{base}/logical_unbatched_transition_equivalent_count_expression")
            and expansion["token_ordinal_rule"]
            == "CONTIGUOUS_ONE_BASED_THROUGH_PHYSICAL_TRANSITION_COUNT_V1"
            and expansion["logical_count_distribution_rule"]
            == ("EUCLIDEAN_QUOTIENT_REMAINDER_FIRST_R_TOKENS_PLUS_ONE_V1")
            and expansion["source_state_component_rule"]
            == "COPY_EVALUATED_RESULT_CELL_STATE_COMPONENTS_V1"
            and expansion["candidate_state_component_rule"]
            == "COPY_EVALUATED_RESULT_CELL_STATE_COMPONENTS_V1"
            and expansion["input_symbol_rule"]
            == ("ORDERED_OBJECT_DERIVATION_KIND_THEN_PHYSICAL_TRANSITION_ORDINAL_V1")
            and expansion["candidate_upper_bound_rule"]
            == "COPY_EVALUATED_RESULT_CELL_CERTIFIED_UPPER_BOUND_V1",
            "transition expansion rule differs",
        )

    subject_rows = grammar["ordered_subject_schema_records"]
    constructors = program["ordered_subject_constructor_records"]
    _require(
        len(constructors) == len(subject_rows) == 16,
        "subject constructor count differs",
    )
    constructor_members = {
        "constructor_position",
        "event_kind",
        "constructor_opcode",
        "subject_member_order_source",
        "ordered_value_source_records",
    }
    exact_member_orders = {
        "CACHE_INSERT": recurrence["cache_key_schema"]["ordered_member_names"],
        "TRANSITION_ATTEMPT": recurrence["transition_token_schema"][
            "ordered_member_names"
        ],
        "RESULT_CELL_EMIT": recurrence["result_cell_schema"]["ordered_member_names"],
        "STEP_COMMITMENT_EMIT": recurrence["step_commitment_schema"][
            "ordered_member_names"
        ],
        "FINAL_RESULT_EMIT": grammar["final_result_subject_contract"][
            "ordered_member_names"
        ],
    }
    for position, (subject_row, constructor) in enumerate(
        zip(subject_rows, constructors, strict=True), 1
    ):
        _require(
            set(constructor) == constructor_members,
            "subject constructor members differ",
        )
        _require(
            constructor["constructor_position"] == position
            and constructor["event_kind"] == subject_row["event_kind"],
            "subject constructor order differs",
        )
        sources = constructor["ordered_value_source_records"]
        _require(
            type(sources) is list and bool(sources), "subject constructor is empty"
        )
        _require(
            [row["value_source_position"] for row in sources]
            == list(range(1, len(sources) + 1))
            and all(
                set(row) == {"value_source_position", "member_name", "value_source"}
                and type(row["member_name"]) is str
                and type(row["value_source"]) is str
                for row in sources
            ),
            "subject value-source records differ",
        )
        expected_members = exact_member_orders.get(constructor["event_kind"])
        if expected_members is not None:
            _require(
                [row["member_name"] for row in sources] == expected_members,
                "tagged subject constructor member order differs",
            )

    source_maps = {
        row["event_kind"]: {
            source["member_name"]: source["value_source"]
            for source in row["ordered_value_source_records"]
        }
        for row in constructors
    }
    _require(
        source_maps["LOGICAL_DESCRIPTOR_VISIT"]
        == {
            "logical_step_reference_version": (
                "CONST:riskyieldmm.raw_v8_step2_external_schema_v2."
                "logical_step_reference.v1"
            ),
            "logical_count_plan_id": "PLAN.logical_count_plan_id",
            "subject_variant": "UNIT.subject_variant",
            "logical_derivation_step_position": (
                "UNIT.logical_derivation_step_position"
            ),
            "logical_derivation_step_id": "UNIT.logical_derivation_step_id",
            "derivation_kind": "UNIT.derivation_kind",
        },
        "logical descriptor source map differs",
    )
    _require(
        source_maps["CACHE_INSERT"]["owner_profile_position"]
        == "UNIT.owner_profile_position",
        "cache-key profile source is not unit-closed",
    )
    _require(
        source_maps["STEP_COMMITMENT_EMIT"]["initial_controller_state_id"]
        == "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id"
        and source_maps["STEP_COMMITMENT_EMIT"]["terminal_controller_state_id"]
        == "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id",
        "local commitment endpoint source differs",
    )
    _require(
        all(
            "LOCAL_CATALOG.initial_controller_state_id" not in value
            and "LOCAL_CATALOG.terminal_controller_state_id" not in value
            for source_map in source_maps.values()
            for value in source_map.values()
        ),
        "subject constructor references an absent local-catalog member",
    )

    export_name = program["subject_collection_export_name"]
    _require(
        export_name == "CASE_PROGRAM_EXACT_SUBJECT_COLLECTION",
        "subject collection export differs",
    )
    for case_program in grammar["ordered_case_program_records"]:
        for emission in case_program["ordered_event_emission_records"]:
            _require(
                emission["subject_collection_locator"] == {"source": export_name},
                "case program uses an unresolved subject collection",
            )
            _require(
                emission["cardinality_expression"]
                == {
                    "opcode": "SOURCE_LIST_COUNT",
                    "source_locator": {
                        "event_kind": emission["event_kind"],
                        "program_name": case_program["program_name"],
                        "source": export_name,
                    },
                },
                "case program uses a placeholder event cardinality",
            )

    _require(
        program["ordinary_event_cardinality_program"]
        == {
            "batch_application_count_source": ("STEP.physical_batch_application_count"),
            "cache_insert_count_per_step": 1,
            "descriptor_aggregation_source": (
                "STEP.logical_descriptor_occurrence_count"
            ),
            "descriptor_event_count_per_step": 1,
            "result_cell_count_per_step": 1,
            "step_commitment_count_per_step": 1,
            "transition_count_source": "STEP.physical_transition_count",
        },
        "ordinary event cardinality program differs",
    )
    _require(
        program["local_event_cardinality_program"]
        == {
            "batch_application_count": 0,
            "cache_insert_count_source": (
                "/recurrence_catalog/local_shutdown_analytic_catalog/"
                "fixed_controller_state_count"
            ),
            "descriptor_aggregation_source": (
                "/recurrence_catalog/local_shutdown_analytic_catalog/"
                "fixed_controller_transition_count"
            ),
            "descriptor_event_count": 1,
            "result_cell_count_source": (
                "/recurrence_catalog/local_shutdown_analytic_catalog/"
                "fixed_controller_state_count"
            ),
            "step_commitment_count": 1,
            "transition_count_source": (
                "/recurrence_catalog/local_shutdown_analytic_catalog/"
                "fixed_controller_transition_count"
            ),
        },
        "local event cardinality program differs",
    )


def _validated_case_event_hand_oracles(
    raw: bytes, logical_count_plan_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    value = _parse_strict_canonical_json(
        raw, label="case-level event hand oracles", root_kind="ARRAY"
    )
    _require(type(value) is list and len(value) == 3, "event hand-oracle count differs")
    oracle_members = [
        "oracle_position",
        "oracle_id",
        "ordered_coverage_tags",
        "complete_logical_count_plan",
        "exact_source_objects_or_fixture_locators",
        "ordered_logical_event_tokens",
        "event_stream_preimage_canonical_octets_hex",
        "event_stream_preimage_sha256",
        "ordered_expected_resource_measurements",
        "final_result_canonical_octets_hex",
        "final_result_sha256",
        "ordered_live_set_snapshots",
        "expected_status",
    ]
    token_members = [
        "event_position",
        "execution_phase",
        "logical_derivation_step_position",
        "event_kind",
        "event_ordinal",
        "subject_schema_version",
        "subject_kind",
        "subject_role",
        "subject_ordinal",
        "subject_canonical_octets",
        "subject_sha256",
        "aggregation_multiplicity",
        "logical_unbatched_equivalent_count",
        "observed_value",
    ]
    expected_plan_positions = [67, 68, 475]
    normalized: list[dict[str, Any]] = []
    for oracle_position, (row, plan_position) in enumerate(
        zip(value, expected_plan_positions, strict=True), 1
    ):
        _require(type(row) is dict, "event hand oracle is not an object")
        _require(set(row) == set(oracle_members), "event hand-oracle members differ")
        _require(
            row["oracle_position"] == oracle_position, "event oracle order differs"
        )
        plan = logical_count_plan_records[plan_position - 1]
        _require(
            row["complete_logical_count_plan"] == plan,
            "event oracle logical plan differs",
        )
        tokens = row["ordered_logical_event_tokens"]
        sources = row["exact_source_objects_or_fixture_locators"]
        _require(
            type(tokens) is list
            and type(sources) is list
            and len(tokens) == len(sources)
            and bool(tokens),
            "event oracle token/source cardinality differs",
        )
        normalized_tokens: list[dict[str, Any]] = []
        for event_position, (token, source) in enumerate(
            zip(tokens, sources, strict=True), 1
        ):
            _require(
                set(token) == set(token_members), "event oracle token members differ"
            )
            _require(
                token["event_position"] == event_position
                and source["event_position"] == event_position,
                "event oracle position differs",
            )
            subject_raw = bytes.fromhex(source["subject_canonical_octets_hex"])
            _require(
                token["subject_canonical_octets"] == len(subject_raw)
                and token["subject_sha256"] == _sha256(subject_raw),
                "event oracle subject bytes differ",
            )
            normalized_tokens.append({name: token[name] for name in token_members})
        stream_raw = bytes.fromhex(row["event_stream_preimage_canonical_octets_hex"])
        final_raw = bytes.fromhex(row["final_result_canonical_octets_hex"])
        _require(
            _sha256(stream_raw) == row["event_stream_preimage_sha256"],
            "event oracle stream digest differs",
        )
        _require(
            _sha256(final_raw) == row["final_result_sha256"],
            "event oracle final-result digest differs",
        )
        without_id = {
            name: (
                normalized_tokens
                if name == "ordered_logical_event_tokens"
                else row[name]
            )
            for name in oracle_members
            if name not in {"oracle_id"}
        }
        expected_id = _sha256(
            _canonical_bytes(
                {
                    "domain": ("RiskYieldMMStep2CaseEventHandOracleV1V4_9F_RawV8"),
                    "payload": without_id,
                }
            )
        )
        _require(row["oracle_id"] == expected_id, "event hand-oracle ID differs")
        normalized.append(
            {
                "oracle_position": oracle_position,
                "oracle_id": expected_id,
                **{
                    name: without_id[name]
                    for name in oracle_members
                    if name not in {"oracle_position", "oracle_id"}
                },
            }
        )
    return normalized


def _event_catalog(
    identity_records: list[dict[str, Any]],
    case_event_grammar: dict[str, Any],
) -> dict[str, Any]:
    metric_programs: dict[str, tuple[tuple[int, str, str], ...]] = {
        "CASE_OPEN": ((1, "ADD", "ONE"),),
        "LOGICAL_DESCRIPTOR_VISIT": ((2, "ADD", "AGGREGATION_MULTIPLICITY"),),
        "CACHE_INSERT": (
            (7, "ADD", "ONE"),
            (8, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
        ),
        "TRANSITION_ATTEMPT": (
            (4, "ADD", "ONE"),
            (5, "ADD", "LOGICAL_UNBATCHED_EQUIVALENT_COUNT"),
            (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
            (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
        ),
        "BATCH_APPLICATION": ((6, "ADD", "ONE"),),
        "RESULT_CELL_EMIT": (
            (3, "ADD", "ONE"),
            (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
        ),
        "STEP_COMMITMENT_EMIT": (),
        "FINAL_RESULT_EMIT": ((18, "ADD", "SUBJECT_CANONICAL_OCTETS"),),
        "INTRINSIC_RULE_EVALUATION": ((12, "ADD", "AGGREGATION_MULTIPLICITY"),),
        "CROSS_RULE_EVALUATION": ((13, "ADD", "AGGREGATION_MULTIPLICITY"),),
        "APPLICATION_EVALUATION": ((14, "ADD", "AGGREGATION_MULTIPLICITY"),),
        "HASH_PREIMAGE": ((11, "ADD", "SUBJECT_CANONICAL_OCTETS"),),
        "RETENTION_OBSERVATION": ((17, "MAX", "OBSERVED_VALUE"),),
        "DERIVATION_DEPTH_OBSERVATION": ((15, "MAX", "OBSERVED_VALUE"),),
        "ITERATION_DEPTH_OBSERVATION": ((16, "MAX", "OBSERVED_VALUE"),),
        "EVENT_STREAM_CLOSE": (),
    }
    subjects = case_event_grammar["ordered_subject_schema_records"]
    phases = [
        row["execution_phase"]
        for row in case_event_grammar["ordered_execution_phase_records"]
    ]
    _require(
        [row["event_kind"] for row in subjects] == list(metric_programs),
        "event subject order differs from metric program order",
    )
    payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_event_catalog.v2"
        ),
        "event_schema": {
            "ordered_member_names": [
                "event_position",
                "execution_phase",
                "logical_derivation_step_position",
                "event_kind",
                "event_ordinal",
                "subject_schema_version",
                "subject_kind",
                "subject_role",
                "subject_ordinal",
                "subject_canonical_octets",
                "subject_sha256",
                "aggregation_multiplicity",
                "logical_unbatched_equivalent_count",
                "observed_value",
            ],
            "subject_digest_algorithm": "SHA256",
            "subject_bytes_are_recomputed": True,
        },
        "metric_update_schema": {
            "ordered_member_names": [
                "metric_position",
                "update_kind",
                "value_source",
            ],
            "update_kind_enum": ["ADD", "MAX"],
            "value_source_enum": [
                "ONE",
                "SUBJECT_CANONICAL_OCTETS",
                "AGGREGATION_MULTIPLICITY",
                "LOGICAL_UNBATCHED_EQUIVALENT_COUNT",
                "OBSERVED_VALUE",
            ],
        },
        "ordered_event_kind_records": [
            {
                "event_kind_position": position,
                "event_kind": subject["event_kind"],
                "subject_schema_version": subject["subject_schema_version"],
                "ordered_allowed_execution_phases": phases,
                "ordered_metric_update_program": [
                    {
                        "metric_position": metric_position,
                        "update_kind": update_kind,
                        "value_source": value_source,
                    }
                    for metric_position, update_kind, value_source in metric_programs[
                        subject["event_kind"]
                    ]
                ],
            }
            for position, subject in enumerate(subjects, 1)
        ],
        "case_level_event_grammar": case_event_grammar,
    }
    return {
        **payload,
        "logical_event_catalog_id": _semantic_id(
            _identity_domain(identity_records, "LOGICAL_EVENT_CATALOG"), payload
        ),
    }


def _validate_template_schema_graph(registry: dict[str, Any]) -> int:
    schemas = registry["value_schema_catalog"]
    descriptors = registry["ordered_external_type_descriptors"]
    schema_ids = [row["value_schema_id"] for row in schemas]
    type_names = [row["type_name"] for row in descriptors]
    _require(len(schema_ids) == len(set(schema_ids)), "duplicate value-schema ID")
    _require(len(type_names) == len(set(type_names)), "duplicate type name")
    schema_by_id = {row["value_schema_id"]: row for row in schemas}
    descriptor_by_name = {row["type_name"]: row for row in descriptors}
    graph: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for schema_id, schema in schema_by_id.items():
        node = ("VALUE_SCHEMA", schema_id)
        edges: list[tuple[str, str]] = []
        if schema["schema_kind"] == "OBJECT_REF":
            target = schema["referenced_type_name"]
            _require(target in descriptor_by_name, f"unknown referenced type: {target}")
            edges.append(("TYPE", target))
        elif schema["schema_kind"] == "ARRAY":
            target = schema["array_item_value_schema_id"]
            _require(target in schema_by_id, f"unknown array-item schema: {target}")
            edges.append(("VALUE_SCHEMA", target))
        graph[node] = edges
    for type_name, descriptor in descriptor_by_name.items():
        node = ("TYPE", type_name)
        edges = []
        if descriptor["type_form"] == "RECORD":
            for member in descriptor["record_member_descriptors"]:
                target = member["value_schema_id"]
                _require(target in schema_by_id, f"unknown member schema: {target}")
                edges.append(("VALUE_SCHEMA", target))
        else:
            for alternative in descriptor["tagged_union_descriptor"][
                "ordered_alternatives"
            ]:
                target = alternative["referenced_type_name"]
                _require(target in descriptor_by_name, f"unknown union type: {target}")
                edges.append(("TYPE", target))
        graph[node] = edges
    _require(len(graph) == 288, "template schema graph node count differs")
    colors: dict[tuple[str, str], int] = {}
    maximum_depth = 0

    def visit(node: tuple[str, str], depth: int) -> None:
        nonlocal maximum_depth
        color = colors.get(node, 0)
        _require(color != 1, f"template schema graph cycle at {node}")
        if color == 2:
            return
        colors[node] = 1
        maximum_depth = max(maximum_depth, depth)
        for child in graph[node]:
            visit(child, depth + 1)
        colors[node] = 2

    for node in graph:
        visit(node, 0)
    _require(len(colors) == len(graph), "template schema graph closure differs")
    _require(maximum_depth == 12, "template schema graph maximum depth differs")
    return maximum_depth


def _safe_integer_probe_values(integer_minimum: int, integer_maximum: int) -> list[int]:
    _require(
        type(integer_minimum) is int
        and type(integer_maximum) is int
        and 0 <= integer_minimum <= integer_maximum <= SAFE_INTEGER_MAXIMUM,
        "safe-integer interval differs",
    )
    values = {integer_minimum, integer_maximum}
    if integer_minimum == 0:
        values.add(0)
    for exponent in range(1, 17):
        for value in (10**exponent - 1, 10**exponent):
            if integer_minimum <= value <= integer_maximum:
                values.add(value)
    return sorted(values)


def _build_plan_templates(
    identity_records: list[dict[str, Any]],
    registry: dict[str, Any],
    recurrence: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str | None], str]]:
    _validate_template_schema_graph(registry)
    value_schemas = registry["value_schema_catalog"]
    value_by_id = {row["value_schema_id"]: row for row in value_schemas}
    value_position = {
        row["value_schema_id"]: position
        for position, row in enumerate(value_schemas, 1)
    }
    languages = {
        row["text_language_id"]: (position, row)
        for position, row in enumerate(registry["text_language_catalog"], 1)
    }
    descriptors = registry["ordered_external_type_descriptors"]
    descriptor_by_name = {row["type_name"]: row for row in descriptors}
    descriptor_position = {
        row["type_name"]: position for position, row in enumerate(descriptors, 1)
    }
    kernel_by_kind = {
        row["derivation_kind"]: row
        for row in recurrence["ordered_derivation_kernel_records"]
    }
    cache_key_schema_version = recurrence["cache_key_schema"]["cache_key_version"]
    batch_equivalence_id = recurrence["homogeneous_run_batch_equivalence"][
        "batch_equivalence_id"
    ]
    relaxation_by_name = {
        row["relaxation_name"]: row["safe_relaxation_rule_id"]
        for row in recurrence["ordered_safe_relaxation_records"]
    }
    minimum_schema_cache: dict[str, int] = {}
    minimum_type_cache: dict[tuple[str, str | None], int] = {}

    def minimum_schema_octets(schema_id: str) -> int:
        if schema_id in minimum_schema_cache:
            return minimum_schema_cache[schema_id]
        schema = value_by_id[schema_id]
        kind = schema["schema_kind"]
        if kind == "EXACT_BOOLEAN":
            minimum = len(_canonical_bytes(schema["boolean_literal"]))
        elif kind == "SAFE_INTEGER":
            minimum = min(
                len(_canonical_bytes(value))
                for value in _safe_integer_probe_values(
                    schema["integer_minimum"], schema["integer_maximum"]
                )
            )
        elif kind == "TEXT":
            _, language = languages[schema["text_language_id"]]
            if language["language_kind"] in {"LITERAL", "ENUM"}:
                minimum = min(
                    len(_canonical_bytes(value))
                    for value in language["ordered_literals"]
                )
            elif (
                language["language_kind"] == "BUILTIN"
                and language["built_in_language_kind"] == "LOWERCASE_SHA256"
            ):
                minimum = 66
            else:
                minimum = 2
        elif kind == "OBJECT_REF":
            minimum = minimum_type_octets(schema["referenced_type_name"], None)
        elif kind == "ARRAY":
            count = schema["array_minimum_items"]
            item_minimum = minimum_schema_octets(schema["array_item_value_schema_id"])
            minimum = 2 if count == 0 else 2 + count * item_minimum + max(count - 1, 0)
        else:
            _fail(f"minimum schema kind differs: {kind}")
        if schema["nullable"]:
            minimum = min(4, minimum)
        minimum_schema_cache[schema_id] = minimum
        return minimum

    def minimum_type_octets(type_name: str, alternative_name: str | None) -> int:
        key = (type_name, alternative_name)
        if key in minimum_type_cache:
            return minimum_type_cache[key]
        descriptor = descriptor_by_name[type_name]
        if descriptor["type_form"] == "RECORD":
            members = descriptor["record_member_descriptors"]
            syntax = (
                2
                + max(len(members) - 1, 0)
                + sum(
                    len(_canonical_bytes(member["member_name"])) + 1
                    for member in members
                )
            )
            minimum = syntax + sum(
                minimum_schema_octets(member["value_schema_id"]) for member in members
            )
        else:
            alternatives = descriptor["tagged_union_descriptor"]["ordered_alternatives"]
            selected = [
                row
                for row in alternatives
                if alternative_name is None
                or row["alternative_name"] == alternative_name
            ]
            _require(bool(selected), f"minimum union alternative differs: {key}")
            minimum = min(
                minimum_type_octets(row["referenced_type_name"], None)
                for row in selected
            )
        minimum_type_cache[key] = minimum
        return minimum

    def owner_payload_codec_coordinate(
        descriptor: dict[str, Any], alternative_name: str | None
    ) -> dict[str, Any] | None:
        if descriptor["type_form"] != "TAGGED_UNION" or alternative_name is None:
            return None
        union = descriptor["tagged_union_descriptor"]
        if union["payload_binding_scope"] != "OWNER_MEMBER":
            _require(
                union["payload_binding_scope"] == "SELF_VALUE"
                and union["payload_owner_type_name"] is None
                and union["payload_typed_member_path"] == [],
                "self-value union binding differs",
            )
            return None
        owner_name = union["payload_owner_type_name"]
        path = union["payload_typed_member_path"]
        _require(
            type(owner_name) is str and path and len(path) == 1,
            "owner payload coordinate differs",
        )
        owner = descriptor_by_name[owner_name]
        _require(owner["type_form"] == "RECORD", "union owner is not a record")
        selected = next(
            row
            for row in union["ordered_alternatives"]
            if row["alternative_name"] == alternative_name
        )
        discriminator_values = {
            row["member_name"]: row["text_value"]
            for row in selected["ordered_discriminator_literals"]
        }
        members = owner["record_member_descriptors"]
        syntax = (
            2
            + max(len(members) - 1, 0)
            + sum(
                len(_canonical_bytes(member["member_name"])) + 1 for member in members
            )
        )
        payload_member_name = path[0]
        sibling_minimum = syntax
        payload_count = 0
        for member in members:
            if member["member_name"] == payload_member_name:
                payload_count += 1
                continue
            sibling_minimum += (
                len(_canonical_bytes(discriminator_values[member["member_name"]]))
                if member["member_name"] in discriminator_values
                else minimum_schema_octets(member["value_schema_id"])
            )
        _require(payload_count == 1, "union payload owner member differs")
        owner_ceiling = owner["codec_octet_limit"] - int(
            owner["codec_byte_bound_relation"] == "LT"
        )
        _require(owner_ceiling >= sibling_minimum, "owner payload residual is empty")
        return {
            "coordinate_position": 2,
            "coordinate_scope": "OWNER_PAYLOAD_RESIDUAL",
            "codec_owner_type_name": owner_name,
            "codec_owner_typed_member_path": path,
            "codec_byte_bound_relation": owner["codec_byte_bound_relation"],
            "codec_octet_limit": owner["codec_octet_limit"],
            "minimum_sibling_and_syntax_octets": sibling_minimum,
            "derived_payload_octet_ceiling": owner_ceiling - sibling_minimum,
            "selected_union_alternative_name": alternative_name,
        }

    templates: list[dict[str, Any]] = []
    template_ids: dict[tuple[str, str | None], str] = {}

    def build(root_type_name: str, root_alternative_name: str | None) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        active_types: list[str] = []

        def emit(
            *,
            kind: str,
            locator: dict[str, Any],
            value_schema_id: str | None,
            type_name: str | None,
            alternative_name: str | None,
            parameters: dict[str, Any],
            children: list[int],
            logical_multiplicity: int,
            transition_count: int,
            batch_count: int,
            intrinsic_rule_ids: list[str],
            counts_as_logical_descriptor: bool = True,
        ) -> int:
            _require(
                0 <= logical_multiplicity <= SAFE_INTEGER_MAXIMUM,
                "template logical multiplicity exceeds safe integer",
            )
            _require(kind in kernel_by_kind, f"template kernel is absent: {kind}")
            expected_parameters = set(
                kernel_by_kind[kind]["ordered_parameter_member_names"]
            )
            _require(
                set(parameters) == expected_parameters,
                f"{kind} recurrence parameter members differ",
            )
            meter_program = kernel_by_kind[kind]["meter_program"]
            derived_transition_count = _evaluate_u128_expression(
                meter_program["transition_attempt_count_expression"],
                parameters=parameters,
                logical_transfer_multiplicity=logical_multiplicity,
            )
            derived_logical_transition_count = _evaluate_u128_expression(
                meter_program[
                    "logical_unbatched_transition_equivalent_count_expression"
                ],
                parameters=parameters,
                logical_transfer_multiplicity=logical_multiplicity,
            )
            derived_batch_count = _evaluate_u128_expression(
                meter_program["batch_application_count_expression"],
                parameters=parameters,
                logical_transfer_multiplicity=logical_multiplicity,
            )
            _require(
                transition_count == derived_transition_count,
                f"{kind} physical transition count differs from its meter program",
            )
            _require(
                batch_count == derived_batch_count,
                f"{kind} batch count differs from its meter program",
            )
            record = {
                "template_step_position": len(steps) + 1,
                "derivation_kind": kind,
                "subject_locator": locator,
                "value_schema_id": value_schema_id,
                "type_name": type_name,
                "alternative_name": alternative_name,
                "ordered_child_step_positions": children,
                "recurrence_parameters": parameters,
                "logical_descriptor_occurrence_count": (
                    logical_multiplicity if counts_as_logical_descriptor else 0
                ),
                "logical_transfer_multiplicity": logical_multiplicity,
                "physical_transition_count": transition_count,
                "logical_unbatched_transition_equivalent_count": (
                    derived_logical_transition_count
                ),
                "physical_batch_application_count": batch_count,
                "ordered_intrinsic_rule_ids": intrinsic_rule_ids,
                "kernel_record_sha256": kernel_by_kind[kind]["kernel_record_sha256"],
                "state_signature_id": kernel_by_kind[kind]["state_signature_id"],
                "cache_key_schema_version": cache_key_schema_version,
                "batch_equivalence_id": (
                    batch_equivalence_id
                    if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH"
                    else None
                ),
            }
            identity = _identity_domain(identity_records, "LOGICAL_DERIVATION_STEP")
            steps.append(
                {
                    **record,
                    "logical_derivation_step_id": _semantic_id(identity, record),
                }
            )
            return len(steps)

        def schema_locator(
            schema_id: str, path: list[dict[str, Any]]
        ) -> dict[str, Any]:
            return {
                "locator_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2.template_locator.v1"
                ),
                "registry_object_kind": "VALUE_SCHEMA",
                "registry_position": value_position[schema_id],
                "canonical_json_pointer": (
                    f"/external_schema_registry_v2/value_schema_catalog/"
                    f"{value_position[schema_id] - 1}"
                ),
                "typed_path": path,
            }

        def type_locator(type_name: str, path: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "locator_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2.template_locator.v1"
                ),
                "registry_object_kind": "TYPE_DESCRIPTOR",
                "registry_position": descriptor_position[type_name],
                "canonical_json_pointer": (
                    "/external_schema_registry_v2/ordered_external_type_descriptors/"
                    f"{descriptor_position[type_name] - 1}"
                ),
                "typed_path": path,
            }

        def expand_schema(
            schema_id: str,
            *,
            path: list[dict[str, Any]],
            logical_multiplicity: int,
        ) -> int:
            schema = value_by_id[schema_id]
            schema_kind = schema["schema_kind"]
            locator = schema_locator(schema_id, path)
            children: list[int] = []
            parameters: dict[str, Any]
            transition_count = 1
            batch_count = 0
            if schema_kind == "EXACT_BOOLEAN":
                kind = "EXACT_BOOLEAN"
                parameters = {"boolean_literal": schema["boolean_literal"]}
                transition_count = 1 + int(schema["boolean_literal"] is None)
            elif schema_kind == "SAFE_INTEGER":
                kind = "SAFE_INTEGER_BAND"
                parameters = {
                    "integer_minimum": schema["integer_minimum"],
                    "integer_maximum": schema["integer_maximum"],
                    "ordered_probe_values": _safe_integer_probe_values(
                        schema["integer_minimum"], schema["integer_maximum"]
                    ),
                }
                transition_count = len(parameters["ordered_probe_values"])
            elif schema_kind == "TEXT":
                language_position, language = languages[schema["text_language_id"]]
                language_kind = language["language_kind"]
                if language_kind in {"LITERAL", "ENUM"}:
                    kind = "TEXT_FINITE"
                    parameters = {
                        "text_language_position": language_position,
                        "text_language_id": language["text_language_id"],
                        "ordered_literals": language["ordered_literals"],
                    }
                    transition_count = len(language["ordered_literals"])
                elif (
                    language_kind == "BUILTIN"
                    and language["built_in_language_kind"] == "LOWERCASE_SHA256"
                ):
                    kind = "TEXT_BUILTIN_BOUNDED"
                    parameters = {
                        "text_language_position": language_position,
                        "text_language_id": language["text_language_id"],
                        "built_in_language_kind": "LOWERCASE_SHA256",
                        "minimum_canonical_octets": 66,
                        "maximum_canonical_octets": 66,
                    }
                else:
                    kind = "TEXT_BOUNDED_LANGUAGE"
                    parameters = {
                        "text_language_position": language_position,
                        "text_language_id": language["text_language_id"],
                        "language_kind": language_kind,
                        "built_in_language_kind": language["built_in_language_kind"],
                        "ascii_dfa_id": language["ascii_dfa_id"],
                        "unicode_identifier_profile_id": language[
                            "unicode_identifier_profile_id"
                        ],
                        "minimum_utf8_octets": language["minimum_utf8_octets"],
                        "maximum_utf8_octets": language["maximum_utf8_octets"],
                        "minimum_decoded_octets": language["minimum_decoded_octets"],
                        "maximum_decoded_octets": language["maximum_decoded_octets"],
                        "decimal_maximum": language["decimal_maximum"],
                    }
            elif schema_kind == "OBJECT_REF":
                kind = "OBJECT_REFERENCE"
                child = expand_type(
                    schema["referenced_type_name"],
                    alternative_name=None,
                    path=path,
                    logical_multiplicity=logical_multiplicity,
                )
                children = [child]
                parameters = {
                    "referenced_type_name": schema["referenced_type_name"],
                    "child_step_position": child,
                }
            elif schema_kind == "ARRAY":
                kind = "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH"
                maximum_items = schema["array_maximum_items"]
                item_multiplier = logical_multiplicity * maximum_items
                child = expand_schema(
                    schema["array_item_value_schema_id"],
                    path=[
                        *path,
                        {
                            "path_step_kind": "ARRAY_ITEM_TEMPLATE",
                            "member_name": None,
                            "union_alternative_name": None,
                        },
                    ],
                    logical_multiplicity=item_multiplier,
                )
                children = [child]
                observer_payload = {
                    "closure_version": (
                        "riskyieldmm.raw_v8_step2_external_schema_v2."
                        "array_observer_closure.v1"
                    ),
                    "array_value_schema_id": schema_id,
                    "array_typed_path": path,
                    "ordered_observer_records": [
                        {
                            "observer_position": 1,
                            "observer_kind": "ORDINAL_ORDER_UNIQUENESS",
                            "status": "DROPPED_COMPLETE_PREDICATE",
                            "safe_relaxation_rule_id": relaxation_by_name[
                                "DROP_ARRAY_ORDER_AND_UNIQUENESS_TO_SEQUENCE_SUPERSET_V1"
                            ],
                            "surviving_summary_component": None,
                        },
                        {
                            "observer_position": 2,
                            "observer_kind": "INTRINSIC_CROSS_APPLICATION_RULE",
                            "status": "DROPPED_COMPLETE_PREDICATE",
                            "safe_relaxation_rule_id": relaxation_by_name[
                                "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
                            ],
                            "surviving_summary_component": None,
                        },
                        {
                            "observer_position": 3,
                            "observer_kind": "PAYLOAD_DERIVED_IDENTITY_RELATION",
                            "status": "DROPPED_EQUALITY_RETAIN_FIXED_WIDTH",
                            "safe_relaxation_rule_id": relaxation_by_name[
                                "DERIVED_IDENTITY_FIXED_WIDTH_PAYLOAD_SUPERSET_V1"
                            ],
                            "surviving_summary_component": None,
                        },
                        {
                            "observer_position": 4,
                            "observer_kind": "CARDINALITY_AND_CANONICAL_BOUNDARY",
                            "status": "RETAINED_IN_BATCH_STATE",
                            "safe_relaxation_rule_id": None,
                            "surviving_summary_component": (
                                "ITEM_COUNT,CAPPED_ITEM_UPPER_OCTET_SUM,COMMA_COUNT"
                            ),
                        },
                        {
                            "observer_position": 5,
                            "observer_kind": "ANCESTOR_CODEC_LENGTH",
                            "status": "RETAINED_BY_EFFECTIVE_CEILING_INTERSECTION",
                            "safe_relaxation_rule_id": None,
                            "surviving_summary_component": (
                                "CAPPED_ITEM_UPPER_OCTET_SUM,COMMA_COUNT"
                            ),
                        },
                    ],
                    "surviving_state_signature_id": kernel_by_kind[kind][
                        "state_signature_id"
                    ],
                    "batch_eligible": True,
                    "proof_rule": (
                        "NO_SURVIVING_ORDINAL_DISTINGUISHER_AND_ASSOCIATIVE_"
                        "COMPLETE_SUMMARY_STATE"
                    ),
                }
                observer_closure = {
                    **observer_payload,
                    "array_observer_closure_id": _semantic_id(
                        _identity_domain(identity_records, "ARRAY_OBSERVER_CLOSURE"),
                        observer_payload,
                    ),
                }
                parameters = {
                    "minimum_items": schema["array_minimum_items"],
                    "maximum_items": maximum_items,
                    "item_value_schema_id": schema["array_item_value_schema_id"],
                    "item_step_position": child,
                    "ordered_run_records": [
                        {
                            "run_position": 1,
                            "first_array_ordinal": 0,
                            "item_count": maximum_items,
                            "item_step_position": child,
                            "array_observer_closure_id": observer_closure[
                                "array_observer_closure_id"
                            ],
                        }
                    ],
                    "observer_closure_record": observer_closure,
                }
                transition_count = 2 if maximum_items else 1
                batch_count = int(maximum_items > 0)
            else:
                _fail(f"unknown value schema kind: {schema_kind}")
            step = emit(
                kind=kind,
                locator=locator,
                value_schema_id=schema_id,
                type_name=None,
                alternative_name=None,
                parameters=parameters,
                children=children,
                logical_multiplicity=logical_multiplicity,
                transition_count=transition_count,
                batch_count=batch_count,
                intrinsic_rule_ids=[],
                counts_as_logical_descriptor=not schema["nullable"],
            )
            if schema["nullable"]:
                step = emit(
                    kind="NULLABLE_BRANCH",
                    locator=locator,
                    value_schema_id=schema_id,
                    type_name=None,
                    alternative_name=None,
                    parameters={"child_step_position": step},
                    children=[step],
                    logical_multiplicity=logical_multiplicity,
                    transition_count=3,
                    batch_count=0,
                    intrinsic_rule_ids=[],
                    counts_as_logical_descriptor=True,
                )
            return step

        def expand_type(
            type_name: str,
            *,
            alternative_name: str | None,
            path: list[dict[str, Any]],
            logical_multiplicity: int,
        ) -> int:
            _require(type_name not in active_types, f"type graph cycle at {type_name}")
            active_types.append(type_name)
            descriptor = descriptor_by_name[type_name]
            locator = type_locator(type_name, path)
            children: list[int] = []
            if descriptor["type_form"] == "RECORD":
                _require(alternative_name is None, "record selected as an alternative")
                member_records = []
                for member in descriptor["record_member_descriptors"]:
                    child = expand_schema(
                        member["value_schema_id"],
                        path=[
                            *path,
                            {
                                "path_step_kind": "RECORD_MEMBER",
                                "member_name": member["member_name"],
                                "union_alternative_name": None,
                            },
                        ],
                        logical_multiplicity=logical_multiplicity,
                    )
                    children.append(child)
                    member_records.append(
                        {
                            "member_position": member["member_position"],
                            "member_name": member["member_name"],
                            "member_role": member["member_role"],
                            "member_name_canonical_octets": len(
                                _canonical_bytes(member["member_name"])
                            ),
                            "child_step_position": child,
                        }
                    )
                record_step = emit(
                    kind="RECORD_MEMBER_FOLD",
                    locator=locator,
                    value_schema_id=None,
                    type_name=type_name,
                    alternative_name=None,
                    parameters={
                        "ordered_member_records": member_records,
                        "record_member_count": len(member_records),
                        "record_syntax_octets_excluding_child_values": (
                            2
                            + max(len(member_records) - 1, 0)
                            + sum(
                                row["member_name_canonical_octets"] + 1
                                for row in member_records
                            )
                        ),
                    },
                    children=children,
                    logical_multiplicity=logical_multiplicity,
                    transition_count=len(children) + 1,
                    batch_count=0,
                    intrinsic_rule_ids=descriptor["ordered_intrinsic_rule_ids"],
                    counts_as_logical_descriptor=False,
                )
            else:
                union = descriptor["tagged_union_descriptor"]
                alternatives = union["ordered_alternatives"]
                selected = (
                    alternatives
                    if alternative_name is None
                    else [
                        row
                        for row in alternatives
                        if row["alternative_name"] == alternative_name
                    ]
                )
                _require(
                    bool(selected), f"union alternative is absent: {alternative_name}"
                )
                alternative_records = []
                for alternative in selected:
                    child = expand_type(
                        alternative["referenced_type_name"],
                        alternative_name=None,
                        path=[
                            *path,
                            {
                                "path_step_kind": "UNION_ALTERNATIVE",
                                "member_name": None,
                                "union_alternative_name": alternative[
                                    "alternative_name"
                                ],
                            },
                        ],
                        logical_multiplicity=logical_multiplicity,
                    )
                    children.append(child)
                    alternative_records.append(
                        {
                            "alternative_position": alternative["alternative_position"],
                            "alternative_name": alternative["alternative_name"],
                            "referenced_type_name": alternative["referenced_type_name"],
                            "ordered_discriminator_literals": alternative[
                                "ordered_discriminator_literals"
                            ],
                            "child_step_position": child,
                        }
                    )
                record_step = emit(
                    kind="TAGGED_UNION_BRANCH",
                    locator=locator,
                    value_schema_id=None,
                    type_name=type_name,
                    alternative_name=alternative_name,
                    parameters={
                        "ordered_alternative_records": alternative_records,
                        "owner_type_name": union["payload_owner_type_name"],
                        "owner_typed_member_path": union["payload_typed_member_path"],
                    },
                    children=children,
                    logical_multiplicity=logical_multiplicity,
                    transition_count=len(children) + 1,
                    batch_count=0,
                    intrinsic_rule_ids=descriptor["ordered_intrinsic_rule_ids"],
                    counts_as_logical_descriptor=False,
                )
            codec_coordinates = [
                {
                    "coordinate_position": 1,
                    "coordinate_scope": "SELF_TYPE",
                    "codec_owner_type_name": type_name,
                    "codec_owner_typed_member_path": [],
                    "codec_byte_bound_relation": descriptor[
                        "codec_byte_bound_relation"
                    ],
                    "codec_octet_limit": descriptor["codec_octet_limit"],
                    "minimum_sibling_and_syntax_octets": 0,
                    "derived_payload_octet_ceiling": descriptor["codec_octet_limit"]
                    - int(descriptor["codec_byte_bound_relation"] == "LT"),
                    "selected_union_alternative_name": alternative_name,
                }
            ]
            owner_coordinate = owner_payload_codec_coordinate(
                descriptor, alternative_name
            )
            if owner_coordinate is not None:
                codec_coordinates.append(owner_coordinate)
            codec_step = emit(
                kind="CODEC_INTERSECTION",
                locator=locator,
                value_schema_id=None,
                type_name=type_name,
                alternative_name=alternative_name,
                parameters={
                    "ordered_codec_coordinate_records": codec_coordinates,
                    "child_step_position": record_step,
                },
                children=[record_step],
                logical_multiplicity=logical_multiplicity,
                transition_count=len(codec_coordinates) + 1,
                batch_count=0,
                intrinsic_rule_ids=[],
                counts_as_logical_descriptor=True,
            )
            active_types.pop()
            return codec_step

        root_step = expand_type(
            root_type_name,
            alternative_name=root_alternative_name,
            path=[],
            logical_multiplicity=1,
        )
        _require(root_step == len(steps), "template root is not the final step")
        required_relaxation_names: set[str] = set()
        if any(step["ordered_intrinsic_rule_ids"] for step in steps):
            required_relaxation_names.add(
                "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
            )
        if any(
            step["derivation_kind"]
            in {"ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH", "ARRAY_STREAM_FOLD"}
            for step in steps
        ):
            required_relaxation_names.add(
                "DROP_ARRAY_ORDER_AND_UNIQUENESS_TO_SEQUENCE_SUPERSET_V1"
            )
        if any(step["derivation_kind"] == "TEXT_BOUNDED_LANGUAGE" for step in steps):
            required_relaxation_names.add(
                "DROP_COMPLETE_TEXT_LANGUAGE_TO_JSON_STRING_SUPERSET_V1"
            )
        if any(
            step["type_name"] is not None
            and descriptor_by_name[step["type_name"]]["identity_field"] is not None
            for step in steps
        ):
            required_relaxation_names.add(
                "DERIVED_IDENTITY_FIXED_WIDTH_PAYLOAD_SUPERSET_V1"
            )
        required_relaxation_ids = [
            row["safe_relaxation_rule_id"]
            for row in recurrence["ordered_safe_relaxation_records"]
            if row["relaxation_name"] in required_relaxation_names
        ]
        _require(
            len(required_relaxation_ids) == len(required_relaxation_names),
            "template relaxation closure differs",
        )
        relaxation_application_records: list[dict[str, Any]] = []

        def add_relaxation_application(
            *,
            rule_name: str,
            predicate_kind: str,
            predicate_id: str,
            step: dict[str, Any],
            supporting_closure_id: str | None = None,
        ) -> None:
            relaxation_application_records.append(
                {
                    "application_position": len(relaxation_application_records) + 1,
                    "safe_relaxation_rule_id": relaxation_by_name[rule_name],
                    "predicate_kind": predicate_kind,
                    "authority_predicate_id": predicate_id,
                    "logical_derivation_step_position": step["template_step_position"],
                    "subject_locator": step["subject_locator"],
                    "supporting_closure_id": supporting_closure_id,
                }
            )

        for step in steps:
            for rule_id in step["ordered_intrinsic_rule_ids"]:
                add_relaxation_application(
                    rule_name="DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1",
                    predicate_kind="INTRINSIC_RULE",
                    predicate_id=rule_id,
                    step=step,
                )
            if step["derivation_kind"] == "TEXT_BOUNDED_LANGUAGE":
                add_relaxation_application(
                    rule_name="DROP_COMPLETE_TEXT_LANGUAGE_TO_JSON_STRING_SUPERSET_V1",
                    predicate_kind="TEXT_LANGUAGE",
                    predicate_id=step["recurrence_parameters"]["text_language_id"],
                    step=step,
                )
            if step["derivation_kind"] == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
                closure = step["recurrence_parameters"]["observer_closure_record"]
                add_relaxation_application(
                    rule_name="DROP_ARRAY_ORDER_AND_UNIQUENESS_TO_SEQUENCE_SUPERSET_V1",
                    predicate_kind="ARRAY_ORDER_AND_UNIQUENESS",
                    predicate_id=step["value_schema_id"],
                    step=step,
                    supporting_closure_id=closure["array_observer_closure_id"],
                )
            if (
                step["derivation_kind"] == "CODEC_INTERSECTION"
                and step["type_name"] is not None
                and descriptor_by_name[step["type_name"]]["identity_field"] is not None
            ):
                descriptor = descriptor_by_name[step["type_name"]]
                add_relaxation_application(
                    rule_name="DERIVED_IDENTITY_FIXED_WIDTH_PAYLOAD_SUPERSET_V1",
                    predicate_kind="PAYLOAD_DERIVED_IDENTITY_EQUALITY",
                    predicate_id=descriptor["external_type_descriptor_id"],
                    step=step,
                )
        template_payload = {
            "template_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.logical_plan_template.v1"
            ),
            "root_type_name": root_type_name,
            "root_alternative_name": root_alternative_name,
            "ordered_template_steps": steps,
            "ordered_relaxation_application_records": (relaxation_application_records),
            "ordered_required_safe_relaxation_rule_ids": required_relaxation_ids,
            "root_step_position": root_step,
        }
        return {
            "template_position": len(templates) + 1,
            **template_payload,
            "logical_plan_template_id": _semantic_id(
                _identity_domain(identity_records, "LOGICAL_PLAN_TEMPLATE"),
                template_payload,
            ),
        }

    for descriptor in descriptors:
        if descriptor["type_form"] == "RECORD":
            keys = [(descriptor["type_name"], None)]
        else:
            keys = [
                (descriptor["type_name"], alternative["alternative_name"])
                for alternative in descriptor["tagged_union_descriptor"][
                    "ordered_alternatives"
                ]
            ]
        for key in keys:
            template = build(*key)
            templates.append(template)
            template_ids[key] = template["logical_plan_template_id"]
    _require(len(templates) == 66, "logical template count differs from 66")
    return templates, template_ids


def _application_schedule_record(
    *,
    position: int,
    application: dict[str, Any],
    invocation_count: int,
    cross_rule_evaluation_count: int,
    schedule_scope: str,
) -> dict[str, Any]:
    return {
        "schedule_position": position,
        "application_name": application["application_name"],
        "rule_application_id": application["rule_application_id"],
        "rule_id": application["rule_id"],
        "schedule_scope": schedule_scope,
        "application_invocation_count": invocation_count,
        "cross_rule_evaluation_count": cross_rule_evaluation_count,
    }


def _profile_scope_summary(
    profile: dict[str, Any], application_by_name: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        application = application_by_name["APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"]
        return {
            "internal_scope_case_count": 1,
            "synthetic_axis_count": 0,
            "constructed_context_occurrence_count": 0,
            "context_record_reference_count": 2,
            "observation_count": 0,
            "application_invocation_count": 1,
            "cross_rule_evaluation_count": 1,
            "direct_cross_expression_node_count": 3,
            "ordered_root_family_schedule_records": [],
            "ordered_application_schedule_records": [
                _application_schedule_record(
                    position=1,
                    application=application,
                    invocation_count=1,
                    cross_rule_evaluation_count=1,
                    schedule_scope="ONE_OUTER_RESULT_FIXTURE",
                )
            ],
        }
    scope_cases = 0
    axes = int(len(profile["ordered_admissible_root_families"]) >= 2)
    constructed = 0
    references = 0
    observations = 0
    applications = 0
    cross_rules = 0
    expression_nodes = 0
    root_family_schedules = []
    application_totals = {
        name: [0, 0]
        for name in (
            "APPLY/SELECTOR_MARKER_CONTRACT_V1",
            "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
            "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
            "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
            "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        )
    }
    for family_position, family in enumerate(
        profile["ordered_admissible_root_families"], 1
    ):
        pairs = family["ordered_instrumentation_mode_attempt_presence_pairs"]
        roles = family["ordered_measured_observation_roles"]
        axes += int(len(pairs) >= 2)
        axes += len(pairs) * int(len(roles) >= 2)
        family_cases = len(pairs) * len(roles)
        scope_cases += family_cases
        observation_count = family["observation_count"]
        selector_present = int(family["selector_present"])
        constructed += family_cases * observation_count
        references += family_cases * (observation_count + 3 + selector_present)
        observations += family_cases * observation_count
        applications += family_cases * (2 * observation_count + 2 + selector_present)
        cross_rules += family_cases * (187 * observation_count + 1 + selector_present)
        expression_nodes += family_cases * (
            1_872 * observation_count + 4 + 3 * selector_present
        )
        per_family_applications = (
            (
                "APPLY/SELECTOR_MARKER_CONTRACT_V1",
                selector_present,
                selector_present,
            ),
            (
                "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
                observation_count,
                observation_count,
            ),
            (
                "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
                observation_count,
                185 * observation_count,
            ),
            ("APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1", 1, observation_count),
            ("APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1", 1, 1),
        )
        for application_name, invocations, rule_evaluations in per_family_applications:
            application_totals[application_name][0] += family_cases * invocations
            application_totals[application_name][1] += family_cases * rule_evaluations
        active_per_family_applications = [
            row for row in per_family_applications if row[1] > 0
        ]
        root_family_schedules.append(
            {
                "root_family_position": family_position,
                "root_family_kind": family["root_family_kind"],
                "selector_catalog_name": family["selector_catalog_name"],
                "selector_catalog_position": family["selector_catalog_position"],
                "selector_present": family["selector_present"],
                "observation_count": observation_count,
                "attempt_presence_pair_count": len(pairs),
                "measured_observation_role_count": len(roles),
                "internal_scope_case_count": family_cases,
                "ordered_application_schedule_records": [
                    _application_schedule_record(
                        position=position,
                        application=application_by_name[application_name],
                        invocation_count=invocations,
                        cross_rule_evaluation_count=rule_evaluations,
                        schedule_scope="PER_INTERNAL_SCOPE_CASE",
                    )
                    for position, (
                        application_name,
                        invocations,
                        rule_evaluations,
                    ) in enumerate(active_per_family_applications, 1)
                ],
            }
        )
    return {
        "internal_scope_case_count": scope_cases,
        "synthetic_axis_count": axes,
        "constructed_context_occurrence_count": constructed,
        "context_record_reference_count": references,
        "observation_count": observations,
        "application_invocation_count": applications,
        "cross_rule_evaluation_count": cross_rules,
        "direct_cross_expression_node_count": expression_nodes,
        "ordered_root_family_schedule_records": root_family_schedules,
        "ordered_application_schedule_records": [
            _application_schedule_record(
                position=position,
                application=application_by_name[application_name],
                invocation_count=counts[0],
                cross_rule_evaluation_count=counts[1],
                schedule_scope="PROFILE_TOTAL",
            )
            for position, (application_name, counts) in enumerate(
                [row for row in application_totals.items() if row[1][0] > 0],
                1,
            )
        ],
    }


_SCOPE_SUMMARY_COUNT_MEMBERS: Final = (
    "internal_scope_case_count",
    "synthetic_axis_count",
    "constructed_context_occurrence_count",
    "context_record_reference_count",
    "observation_count",
    "application_invocation_count",
    "cross_rule_evaluation_count",
    "direct_cross_expression_node_count",
)


def _compact_scope_summary(
    expanded: dict[str, Any],
    *,
    schedule_authority_kind: str,
    schedule_authority_id: str | None,
    application_schedule_operation_position: int | None,
    p2_cross_application_deletion_policy_id: str | None,
) -> dict[str, Any]:
    _require(
        set(_SCOPE_SUMMARY_COUNT_MEMBERS) < set(expanded),
        "expanded scope summary lacks count members",
    )
    return {
        "scope_summary_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.compact_scope_summary.v1"
        ),
        **{name: expanded[name] for name in _SCOPE_SUMMARY_COUNT_MEMBERS},
        "schedule_authority_kind": schedule_authority_kind,
        "schedule_authority_id": schedule_authority_id,
        "application_schedule_operation_position": (
            application_schedule_operation_position
        ),
        "p2_cross_application_deletion_policy_id": (
            p2_cross_application_deletion_policy_id
        ),
    }


def _unescape_json_pointer_token(token: str) -> str:
    output: list[str] = []
    position = 0
    while position < len(token):
        if token[position] != "~":
            output.append(token[position])
            position += 1
            continue
        _require(position + 1 < len(token), "truncated JSON-pointer escape")
        escaped = token[position + 1]
        _require(escaped in {"0", "1"}, "unknown JSON-pointer escape")
        output.append("~" if escaped == "0" else "/")
        position += 2
    return "".join(output)


def _resolve_inventory_pointer(inventory: dict[str, Any], pointer: str) -> Any:
    _require(pointer.startswith("/") and pointer != "/", "invalid inventory pointer")
    value: Any = inventory
    for raw_token in pointer[1:].split("/"):
        token = _unescape_json_pointer_token(raw_token)
        if type(value) is list:
            _require(
                token == "0" or (token.isdecimal() and not token.startswith("0")),
                "noncanonical JSON-pointer array index",
            )
            index = int(token)
            _require(index < len(value), "inventory pointer array index is absent")
            value = value[index]
        else:
            _require(
                type(value) is dict and token in value, "inventory pointer is absent"
            )
            value = value[token]
    return value


def _authority_identity_member_name(value: Any, expected_id: str) -> str:
    _require(type(value) is dict, "fixed authority is not an object")
    matches = [
        name
        for name, member_value in value.items()
        if name.endswith("_id") and member_value == expected_id
    ]
    _require(len(matches) == 1, "fixed authority identity binding is not unique")
    return matches[0]


def _profile_scope_case_records(profile: dict[str, Any]) -> list[dict[str, Any]]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        return [
            {
                "scope_case_position": 1,
                "root_family_position": None,
                "mode_attempt_pair_position": None,
                "observation_role_position": None,
                "measured_sequence_ordinal": None,
            }
        ]
    records: list[dict[str, Any]] = []
    for family_position, family in enumerate(
        profile["ordered_admissible_root_families"], 1
    ):
        for pair_position, _pair in enumerate(
            family["ordered_instrumentation_mode_attempt_presence_pairs"], 1
        ):
            for role_position, role in enumerate(
                family["ordered_measured_observation_roles"], 1
            ):
                if role in {"STARTUP_RECOVERY", "BEFORE_OPERATION"}:
                    ordinal = 0
                elif role == "STABLE_CHECKPOINT":
                    ordinal = profile["selector_position"]
                elif role == "AFTER_OPERATION":
                    ordinal = family["selector_length"] + 1
                else:
                    _require(
                        role == "OPERATION_AGGREGATE",
                        "unknown measured-observation role",
                    )
                    ordinal = family["selector_length"] + 2
                _require(
                    type(ordinal) is int and 0 <= ordinal < family["observation_count"],
                    "measured observation ordinal is outside its root family",
                )
                records.append(
                    {
                        "scope_case_position": len(records) + 1,
                        "root_family_position": family_position,
                        "mode_attempt_pair_position": pair_position,
                        "observation_role_position": role_position,
                        "measured_sequence_ordinal": ordinal,
                    }
                )
    _require(bool(records), "profile has no scope cases")
    return records


def _application_instruction_record(
    *,
    position: int,
    application: dict[str, Any],
    invocation_ordinal_program: str,
    invocation_count: int,
    evaluation_count: int,
) -> dict[str, Any]:
    return {
        "instruction_position": position,
        "application_name": application["application_name"],
        "rule_application_id": application["rule_application_id"],
        "rule_id": application["rule_id"],
        "invocation_ordinal_program": invocation_ordinal_program,
        "application_invocation_count_per_scope_case": invocation_count,
        "cross_rule_evaluation_count_per_scope_case": evaluation_count,
    }


def _profile_schedule_segments(
    profile: dict[str, Any], application_by_name: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        application = application_by_name["APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"]
        return [
            {
                "segment_position": 1,
                "root_family_position": None,
                "scope_case_multiplicity": 1,
                "observation_count": 0,
                "selector_present": False,
                "ordered_application_instruction_records": [
                    _application_instruction_record(
                        position=1,
                        application=application,
                        invocation_ordinal_program="SINGLE_ZERO_NULL_BOUND_V1",
                        invocation_count=1,
                        evaluation_count=1,
                    )
                ],
                "application_invocation_count_per_scope_case": 1,
                "cross_rule_evaluation_count_per_scope_case": 1,
                "direct_cross_expression_node_count_per_scope_case": 3,
            }
        ]

    segments: list[dict[str, Any]] = []
    for family_position, family in enumerate(
        profile["ordered_admissible_root_families"], 1
    ):
        observation_count = family["observation_count"]
        selector_present = bool(family["selector_present"])
        instruction_specs: list[tuple[str, str, int, int]] = []
        if selector_present:
            instruction_specs.append(
                (
                    "APPLY/SELECTOR_MARKER_CONTRACT_V1",
                    "SINGLE_ZERO_NULL_BOUND_V1",
                    1,
                    1,
                )
            )
        instruction_specs.extend(
            [
                (
                    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
                    "ZERO_BASED_OBSERVATION_RANGE_V1",
                    observation_count,
                    observation_count,
                ),
                (
                    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
                    "ZERO_BASED_OBSERVATION_RANGE_V1",
                    observation_count,
                    185 * observation_count,
                ),
                (
                    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
                    "SINGLE_ZERO_NULL_BOUND_V1",
                    1,
                    observation_count,
                ),
                (
                    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
                    "SINGLE_ZERO_NULL_BOUND_V1",
                    1,
                    1,
                ),
            ]
        )
        _require(
            [row[0] for row in instruction_specs]
            == sorted(row[0] for row in instruction_specs),
            "root application instructions are not in lexical order",
        )
        instructions = [
            _application_instruction_record(
                position=position,
                application=application_by_name[name],
                invocation_ordinal_program=ordinal_program,
                invocation_count=invocations,
                evaluation_count=evaluations,
            )
            for position, (
                name,
                ordinal_program,
                invocations,
                evaluations,
            ) in enumerate(instruction_specs, 1)
        ]
        scope_case_multiplicity = len(
            family["ordered_instrumentation_mode_attempt_presence_pairs"]
        ) * len(family["ordered_measured_observation_roles"])
        selector_integer = int(selector_present)
        segments.append(
            {
                "segment_position": family_position,
                "root_family_position": family_position,
                "scope_case_multiplicity": scope_case_multiplicity,
                "observation_count": observation_count,
                "selector_present": selector_present,
                "ordered_application_instruction_records": instructions,
                "application_invocation_count_per_scope_case": (
                    2 * observation_count + 2 + selector_integer
                ),
                "cross_rule_evaluation_count_per_scope_case": (
                    187 * observation_count + 1 + selector_integer
                ),
                "direct_cross_expression_node_count_per_scope_case": (
                    1_872 * observation_count + 4 + 3 * selector_integer
                ),
            }
        )
    return segments


def _profile_conditioned_cell_contract(
    identity_records: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "contract_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "profile_conditioned_cell_contract.v1"
        ),
        "p2_cell_ordered_member_names": [
            "cell_kind",
            "cell_status",
            "certified_lower_bound_octets",
            "certified_upper_bound_octets",
            "attaining_witness_canonical_octets",
            "proof_source_id",
        ],
        "p2_cell_kind_enum": [
            "SUPERSET_UPPER_BOUND",
            "EXACT_ATTAINED_MAXIMUM",
        ],
        "generic_superset_attainability_claimed": False,
        "exact_cell_invariant": (
            "CELL_KIND_EXACT_IMPLIES_LOWER_EQUALS_UPPER_EQUALS_ATTAINING_WITNESS"
        ),
        "p1_p3_acceptance_rule": (
            "EXACT_RETAINED_WITNESS_CONTEXT_LEGAL_AND_CANONICAL_LENGTH_EQUALS_P2_UPPER"
        ),
        "unresolved_or_unattained_policy": "NO_GO",
        "structural_bound_only_acceptance_forbidden": True,
    }
    return {
        **payload,
        "profile_conditioned_cell_contract_id": _semantic_id(
            _identity_domain(identity_records, "PROFILE_CONDITIONED_CELL_CONTRACT"),
            payload,
        ),
    }


def _p2_cross_application_deletion_policy(
    *,
    identity_records: list[dict[str, Any]],
    recurrence: dict[str, Any],
    application_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    named_relaxation = next(
        row
        for row in recurrence["ordered_safe_relaxation_records"]
        if row["relaxation_name"] == "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
    )
    application_names = (
        "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1",
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    )
    _require(
        list(application_names) == sorted(application_names), "P2 policy order differs"
    )
    payload = {
        "policy_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "p2_cross_application_deletion_policy.v1"
        ),
        "safe_relaxation_rule_id": named_relaxation["safe_relaxation_rule_id"],
        "deleted_predicate_class": named_relaxation["deleted_predicate_class"],
        "soundness_rule": named_relaxation["soundness_rule"],
        "ordered_rule_application_mapping_records": [
            {
                "mapping_position": position,
                "rule_application_id": application_by_name[name]["rule_application_id"],
                "rule_id": application_by_name[name]["rule_id"],
            }
            for position, name in enumerate(application_names, 1)
        ],
    }
    return {
        **payload,
        "p2_cross_application_deletion_policy_id": _semantic_id(
            _identity_domain(identity_records, "P2_CROSS_APPLICATION_DELETION_POLICY"),
            payload,
        ),
    }


def _profile_conditioning_transfer_program(
    *,
    profile: dict[str, Any],
    template: dict[str, Any],
    fixed_operations: list[dict[str, Any]],
    scope_operation: dict[str, Any],
    application_operation: dict[str, Any],
    recurrence: dict[str, Any],
    cell_contract: dict[str, Any],
    deletion_policy: dict[str, Any],
) -> dict[str, Any]:
    is_local_analytic = (
        profile["profile_position"] == 3
        and profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
        and profile["operation_kind"] == "LOCAL_SHUTDOWN"
    )
    scheduled_application_ids = sorted(
        {
            instruction["rule_application_id"]
            for segment in application_operation["ordered_schedule_segment_records"]
            for instruction in segment["ordered_application_instruction_records"]
        }
    )
    mapping_order = {
        row["rule_application_id"]: row["mapping_position"]
        for row in deletion_policy["ordered_rule_application_mapping_records"]
    }
    _require(
        all(
            application_id in mapping_order
            for application_id in scheduled_application_ids
        ),
        "scheduled application lacks a P2 deletion-policy row",
    )
    scheduled_application_ids.sort(key=mapping_order.__getitem__)
    deletion_references = [
        {
            "deletion_position": position,
            "application_schedule_position": position,
            "rule_application_id": application_id,
        }
        for position, application_id in enumerate(scheduled_application_ids, 1)
    ]
    if is_local_analytic:
        p2_instructions = [
            {
                "instruction_position": 1,
                "opcode": "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
                "ordered_input_instruction_positions": [],
                "output_type": "P2_SUPERSET_BOUND_CELL",
                "parameters": {
                    "logical_plan_template_id": template["logical_plan_template_id"],
                    "template_root_step_position": template["root_step_position"],
                },
            },
            {
                "instruction_position": 2,
                "opcode": "LOAD_FIXED_AUTHORITY_SET_V1",
                "ordered_input_instruction_positions": [],
                "output_type": "FIXED_AUTHORITY_SET",
                "parameters": {
                    "ordered_fixed_authority_operation_positions": [
                        row["operation_position"] for row in fixed_operations
                    ]
                },
            },
            {
                "instruction_position": 3,
                "opcode": "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
                "ordered_input_instruction_positions": [2],
                "output_type": "P2_EXACT_ATTAINED_CELL",
                "parameters": {
                    "local_shutdown_analytic_catalog_id": recurrence[
                        "local_shutdown_analytic_catalog"
                    ]["local_shutdown_analytic_catalog_id"],
                    "fixed_spec_operation_position": 1,
                },
            },
            {
                "instruction_position": 4,
                "opcode": "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
                "ordered_input_instruction_positions": [3, 1],
                "output_type": "P2_EXACT_ATTAINED_CELL",
                "parameters": {
                    "intersection_rule": (
                        "EXACT_ANALYTIC_UPPER_MUST_NOT_EXCEED_STRUCTURAL_UPPER"
                    ),
                    "empty_structural_cell_policy": "NO_GO",
                    "analytic_above_structural_upper_policy": "NO_GO",
                    "preserve_exact_attained_cell": True,
                },
            },
        ]
        p2_source = "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
        template_relaxation_positions: list[int] = []
        deletion_references = []
        safe_relaxation_ids: list[str] = []
        generic_attainability_claimed: bool | None = None
    else:
        p2_instructions = [
            {
                "instruction_position": 1,
                "opcode": "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
                "ordered_input_instruction_positions": [],
                "output_type": "P2_SUPERSET_BOUND_CELL",
                "parameters": {
                    "logical_plan_template_id": template["logical_plan_template_id"],
                    "template_root_step_position": template["root_step_position"],
                },
            }
        ]
        p2_source = "STRUCTURAL_TEMPLATE_SUPERSET_V1"
        template_relaxation_positions = list(
            range(1, len(template["ordered_relaxation_application_records"]) + 1)
        )
        required_relaxation_ids = {
            *template["ordered_required_safe_relaxation_rule_ids"],
            deletion_policy["safe_relaxation_rule_id"],
        }
        safe_relaxation_ids = [
            row["safe_relaxation_rule_id"]
            for row in recurrence["ordered_safe_relaxation_records"]
            if row["safe_relaxation_rule_id"] in required_relaxation_ids
        ]
        _require(
            len(safe_relaxation_ids) == len(required_relaxation_ids),
            "generic profile P2 relaxation closure differs",
        )
        generic_attainability_claimed = False
    p2_program = {
        "program_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "profile_p2_upper_bound_program.v1"
        ),
        "upper_bound_source": p2_source,
        "ordered_safe_relaxation_rule_ids": safe_relaxation_ids,
        "ordered_template_relaxation_application_record_positions": (
            template_relaxation_positions
        ),
        "p2_cross_application_deletion_policy_id": (
            None
            if is_local_analytic
            else deletion_policy["p2_cross_application_deletion_policy_id"]
        ),
        "application_schedule_operation_position": (
            None if is_local_analytic else application_operation["operation_position"]
        ),
        "ordered_deleted_cross_application_references": deletion_references,
        "ordered_instruction_records": p2_instructions,
        "root_instruction_position": len(p2_instructions),
        "failure_policy": "UNRESOLVED_EMPTY_INVALID_OR_LIMIT_EXCEEDED_NO_GO",
        "generic_attainability_claimed": generic_attainability_claimed,
    }
    p1_p3_instructions = [
        {
            "instruction_position": 1,
            "opcode": "IMPORT_P2_BOUND_CELL_V1",
            "ordered_input_instruction_positions": [],
            "output_type": "P2_BOUND_CELL",
            "parameters": {"p2_root_instruction_position": len(p2_instructions)},
        },
        {
            "instruction_position": 2,
            "opcode": "LOAD_RETAINED_WITNESS_CONTEXT_V1",
            "ordered_input_instruction_positions": [],
            "output_type": "RETAINED_WITNESS_CONTEXT",
            "parameters": {
                "constraint_scope_profile_id": profile[
                    "maximum_constraint_scope_profile_id"
                ],
                "measured_type_name": profile["measured_type_name"],
            },
        },
        {
            "instruction_position": 3,
            "opcode": "LOAD_FIXED_AUTHORITY_SET_V1",
            "ordered_input_instruction_positions": [],
            "output_type": "FIXED_AUTHORITY_SET",
            "parameters": {
                "ordered_fixed_authority_operation_positions": [
                    row["operation_position"] for row in fixed_operations
                ]
            },
        },
        {
            "instruction_position": 4,
            "opcode": "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
            "ordered_input_instruction_positions": [2, 3],
            "output_type": "SELECTED_EXACT_SCOPE_CASE",
            "parameters": {
                "scope_root_operation_position": scope_operation["operation_position"]
            },
        },
        {
            "instruction_position": 5,
            "opcode": "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
            "ordered_input_instruction_positions": [4, 3],
            "output_type": "EXACT_APPLICATION_SCHEDULE",
            "parameters": {
                "application_schedule_operation_position": application_operation[
                    "operation_position"
                ]
            },
        },
        {
            "instruction_position": 6,
            "opcode": ("EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1"),
            "ordered_input_instruction_positions": [2, 3, 5],
            "output_type": "P1_LEGALITY_RESULT",
            "parameters": {
                "execution_mode": "EXACT_CROSS_RULE_APPLICATION_V1",
                "application_schedule_operation_position": application_operation[
                    "operation_position"
                ],
            },
        },
        {
            "instruction_position": 7,
            "opcode": "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
            "ordered_input_instruction_positions": [2],
            "output_type": "MEASURED_CANONICAL_OCTETS",
            "parameters": {"measured_type_name": profile["measured_type_name"]},
        },
        {
            "instruction_position": 8,
            "opcode": "REQUIRE_P1_AND_P3_EQUALITY_V1",
            "ordered_input_instruction_positions": [1, 6, 7],
            "output_type": "PROFILE_MAXIMUM_ACCEPTANCE_RESULT",
            "parameters": {
                "acceptance_rule": (
                    "P1_TRUE_AND_MEASURED_CANONICAL_OCTETS_EQUALS_P2_UPPER"
                )
            },
        },
    ]
    return {
        "program_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "profile_conditioning_dual_channel_program.v1"
        ),
        "cell_contract_id": cell_contract["profile_conditioned_cell_contract_id"],
        "p2_upper_bound_program": p2_program,
        "p1_p3_attainment_program": {
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "profile_p1_p3_attainment_program.v1"
            ),
            "ordered_instruction_records": p1_p3_instructions,
            "root_instruction_position": len(p1_p3_instructions),
            "failure_policy": "UNRESOLVED_EMPTY_INVALID_OR_LIMIT_EXCEEDED_NO_GO",
        },
    }


def _profile_conditioning_program_records(
    *,
    identity_records: list[dict[str, Any]],
    inventory: dict[str, Any],
    recurrence: dict[str, Any],
    template_ids: dict[tuple[str, str | None], str],
    template_by_id: dict[str, dict[str, Any]],
    application_by_name: dict[str, dict[str, Any]],
    cell_contract: dict[str, Any],
    deletion_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    records: list[dict[str, Any]] = []
    for profile in profiles:
        profile_position = profile["profile_position"]
        _require(
            profile_position == len(records) + 1,
            "profile program position differs from profile order",
        )
        template_id = template_ids[(profile["measured_type_name"], None)]
        fixed_operations = []
        for operation_position, (pointer, authority_id) in enumerate(
            zip(
                profile["ordered_source_authority_pointers"],
                profile["ordered_source_authority_ids"],
                strict=True,
            ),
            1,
        ):
            authority = _resolve_inventory_pointer(inventory, pointer)
            authority_raw = _canonical_bytes(authority)
            fixed_operations.append(
                {
                    "operation_position": operation_position,
                    "opcode": "FIXED_VALUE",
                    "inventory_json_pointer": pointer,
                    "identity_member_name": _authority_identity_member_name(
                        authority, authority_id
                    ),
                    "expected_authority_id": authority_id,
                    "fixed_canonical_octets": len(authority_raw),
                    "fixed_canonical_sha256": _sha256(authority_raw),
                }
            )
        profile_raw = _canonical_bytes(profile)
        scope_cases = _profile_scope_case_records(profile)
        scope_operation_position = len(fixed_operations) + 1
        scope_operation = {
            "operation_position": scope_operation_position,
            "opcode": "SCOPE_ROOT",
            "profile_canonical_octets": len(profile_raw),
            "profile_canonical_sha256": _sha256(profile_raw),
            "scope_transfer_kind": (
                "OUTER_RESULT_APPLICATION"
                if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
                else "ROOT_APPLICATION"
            ),
            "measured_template_root_step_position": template_by_id[template_id][
                "root_step_position"
            ],
            "ordered_fixed_authority_operation_positions": list(
                range(1, len(fixed_operations) + 1)
            ),
            "ordered_scope_case_records": scope_cases,
        }
        schedule_segments = _profile_schedule_segments(profile, application_by_name)
        invocation_count = sum(
            row["scope_case_multiplicity"]
            * row["application_invocation_count_per_scope_case"]
            for row in schedule_segments
        )
        evaluation_count = sum(
            row["scope_case_multiplicity"]
            * row["cross_rule_evaluation_count_per_scope_case"]
            for row in schedule_segments
        )
        expression_count = sum(
            row["scope_case_multiplicity"]
            * row["direct_cross_expression_node_count_per_scope_case"]
            for row in schedule_segments
        )
        application_operation = {
            "operation_position": scope_operation_position + 1,
            "opcode": "APPLICATION_SCHEDULE_COUNT",
            "child_operation_position": scope_operation_position,
            "execution_mode": "EXACT_CROSS_RULE_APPLICATION_V1",
            "ordered_schedule_segment_records": schedule_segments,
            "application_invocation_count": invocation_count,
            "cross_rule_evaluation_count": evaluation_count,
            "direct_cross_expression_node_count": expression_count,
        }
        is_local_baseline = (
            profile_position == 3
            and profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
            and profile["operation_kind"] == "LOCAL_SHUTDOWN"
        )
        template = template_by_id[template_id]
        conditioning_strategy = (
            "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
            if is_local_baseline
            else "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1"
        )
        conditioning_transfer_program = _profile_conditioning_transfer_program(
            profile=profile,
            template=template,
            fixed_operations=fixed_operations,
            scope_operation=scope_operation,
            application_operation=application_operation,
            recurrence=recurrence,
            cell_contract=cell_contract,
            deletion_policy=deletion_policy,
        )
        payload = {
            "profile_conditioning_program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "profile_conditioning_program.v1"
            ),
            "program_position": profile_position,
            "case_position": profile_position + 66,
            "profile_position": profile_position,
            "maximum_constraint_scope_profile_id": profile[
                "maximum_constraint_scope_profile_id"
            ],
            "profile_inventory_json_pointer": (
                "/operation_contracts/maximum_constraint_scope_profile_catalog/"
                f"{profile_position - 1}"
            ),
            "profile_kind": profile["profile_kind"],
            "constraint_scope": profile["constraint_scope"],
            "operation_kind": profile["operation_kind"],
            "conditioning_strategy": conditioning_strategy,
            "measured_type_name": profile["measured_type_name"],
            "logical_plan_template_id": template_id,
            "template_root_step_position": template_by_id[template_id][
                "root_step_position"
            ],
            "ordered_fixed_authority_operations": fixed_operations,
            "scope_root_operation": scope_operation,
            "application_schedule_operation": application_operation,
            "conditioning_transfer_program": conditioning_transfer_program,
        }
        records.append(
            {
                **payload,
                "profile_conditioning_program_id": _semantic_id(
                    _identity_domain(identity_records, "PROFILE_CONDITIONING_PROGRAM"),
                    payload,
                ),
            }
        )
    _require(len(records) == 408, "profile-conditioning program count differs")
    return records


def _plan_recipe_catalog(
    identity_records: list[dict[str, Any]],
    recurrence: dict[str, Any],
    registry: dict[str, Any],
    inventory: dict[str, Any],
    cases: dict[str, Any],
) -> dict[str, Any]:
    templates, template_ids = _build_plan_templates(
        identity_records, registry, recurrence
    )
    template_by_id = {row["logical_plan_template_id"]: row for row in templates}
    logical_count_plan_records: list[dict[str, Any]] = []
    case_plan_bindings: list[dict[str, Any]] = []
    application_by_name = {
        row["application_name"]: row
        for row in registry["ordered_rule_application_descriptors"]
    }
    cell_contract = _profile_conditioned_cell_contract(identity_records)
    deletion_policy = _p2_cross_application_deletion_policy(
        identity_records=identity_records,
        recurrence=recurrence,
        application_by_name=application_by_name,
    )
    named_constraint_relaxation_id = deletion_policy["safe_relaxation_rule_id"]
    profile_programs = _profile_conditioning_program_records(
        identity_records=identity_records,
        inventory=inventory,
        recurrence=recurrence,
        template_ids=template_ids,
        template_by_id=template_by_id,
        application_by_name=application_by_name,
        cell_contract=cell_contract,
        deletion_policy=deletion_policy,
    )
    profile_program_by_position = {
        row["profile_position"]: row for row in profile_programs
    }
    total_internal_scope_cases = 0
    total_synthetic_axes = 0
    for case in cases["ordered_case_bindings"]:
        position = case["case_position"]
        binding = case["case_binding"]
        application_schedule_operation_position: int | None = None
        if position <= 66:
            key = (binding["type_name"], binding["alternative_name"])
            scope_summary = {
                "internal_scope_case_count": 1,
                "synthetic_axis_count": 0,
                "constructed_context_occurrence_count": 0,
                "context_record_reference_count": 0,
                "observation_count": 0,
                "application_invocation_count": 0,
                "cross_rule_evaluation_count": 0,
                "direct_cross_expression_node_count": 0,
                "ordered_root_family_schedule_records": [],
                "ordered_application_schedule_records": [],
            }
            template_id = template_ids[key]
            profile_position = None
            profile_program_id = None
        elif position <= 474:
            profile_position = position - 66
            profile = inventory["operation_contracts"][
                "maximum_constraint_scope_profile_catalog"
            ][profile_position - 1]
            key = (profile["measured_type_name"], None)
            template_id = template_ids[key]
            scope_summary = _profile_scope_summary(profile, application_by_name)
            profile_program = profile_program_by_position[profile_position]
            profile_program_id = profile_program["profile_conditioning_program_id"]
            application_operation = profile_program["application_schedule_operation"]
            application_schedule_operation_position = application_operation[
                "operation_position"
            ]
            _require(
                len(
                    profile_program["scope_root_operation"][
                        "ordered_scope_case_records"
                    ]
                )
                == scope_summary["internal_scope_case_count"],
                "profile scope-case program differs from scope summary",
            )
            _require(
                application_operation["application_invocation_count"]
                == scope_summary["application_invocation_count"]
                and application_operation["cross_rule_evaluation_count"]
                == scope_summary["cross_rule_evaluation_count"]
                and application_operation["direct_cross_expression_node_count"]
                == scope_summary["direct_cross_expression_node_count"],
                "profile exact application program differs from scope summary",
            )
            total_internal_scope_cases += scope_summary["internal_scope_case_count"]
            total_synthetic_axes += scope_summary["synthetic_axis_count"]
        else:
            template_id = None
            profile_position = 3
            profile_program_id = None
            scope_summary = {
                "internal_scope_case_count": 1,
                "synthetic_axis_count": 0,
                "constructed_context_occurrence_count": 0,
                "context_record_reference_count": 2,
                "observation_count": 0,
                "application_invocation_count": 1,
                "cross_rule_evaluation_count": 1,
                "direct_cross_expression_node_count": 3,
                "ordered_root_family_schedule_records": [],
                "ordered_application_schedule_records": [
                    _application_schedule_record(
                        position=1,
                        application=application_by_name[
                            "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
                        ],
                        invocation_count=1,
                        cross_rule_evaluation_count=1,
                        schedule_scope="ONE_LOCAL_PROSPECTIVE_RESULT",
                    )
                ],
            }
        is_local_profile_analytic = position == 69
        scope_summary["ordered_context_relaxation_application_records"] = (
            [
                {
                    "application_position": row["schedule_position"],
                    "safe_relaxation_rule_id": named_constraint_relaxation_id,
                    "predicate_kind": "CROSS_RULE_APPLICATION",
                    "rule_application_id": row["rule_application_id"],
                    "rule_id": row["rule_id"],
                    "application_invocation_count": row["application_invocation_count"],
                    "cross_rule_evaluation_count": row["cross_rule_evaluation_count"],
                }
                for row in scope_summary["ordered_application_schedule_records"]
            ]
            if 67 <= position <= 474 and not is_local_profile_analytic
            else []
        )
        required_relaxation_ids: set[str] = set()
        if template_id is not None and not is_local_profile_analytic:
            required_relaxation_ids.update(
                template_by_id[template_id]["ordered_required_safe_relaxation_rule_ids"]
            )
        if 67 <= position <= 474 and not is_local_profile_analytic:
            required_relaxation_ids.add(named_constraint_relaxation_id)
        ordered_required_relaxation_ids = [
            row["safe_relaxation_rule_id"]
            for row in recurrence["ordered_safe_relaxation_records"]
            if row["safe_relaxation_rule_id"] in required_relaxation_ids
        ]
        if position <= 66:
            schedule_authority_kind = "NONE"
            schedule_authority_id = None
            scope_deletion_policy_id = None
        elif position <= 474:
            schedule_authority_kind = "PROFILE_CONDITIONING_PROGRAM"
            schedule_authority_id = profile_program_id
            scope_deletion_policy_id = (
                None
                if is_local_profile_analytic
                else deletion_policy["p2_cross_application_deletion_policy_id"]
            )
        else:
            schedule_authority_kind = "LOCAL_SHUTDOWN_ANALYTIC_CATALOG"
            schedule_authority_id = recurrence["local_shutdown_analytic_catalog"][
                "local_shutdown_analytic_catalog_id"
            ]
            scope_deletion_policy_id = None
        scope_summary = _compact_scope_summary(
            scope_summary,
            schedule_authority_kind=schedule_authority_kind,
            schedule_authority_id=schedule_authority_id,
            application_schedule_operation_position=(
                application_schedule_operation_position
            ),
            p2_cross_application_deletion_policy_id=scope_deletion_policy_id,
        )
        plan_payload = {
            "logical_count_plan_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.logical_count_plan.v3"
            ),
            "case_position": position,
            "case_kind": case["case_kind"],
            "case_binding": binding,
            "upper_bound_mode": (
                "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT"
                if position <= 474 and not is_local_profile_analytic
                else "EXACT_LEGAL_DOMAIN"
            ),
            "recurrence_catalog_id": recurrence["recurrence_catalog_id"],
            "ordered_safe_relaxation_rule_ids": (
                ordered_required_relaxation_ids
                if position <= 474 and not is_local_profile_analytic
                else []
            ),
            "logical_plan_template_id": template_id,
            "profile_conditioning_program_id": profile_program_id,
            "local_analytic_catalog_id": (
                None
                if position <= 474
                else recurrence["local_shutdown_analytic_catalog"][
                    "local_shutdown_analytic_catalog_id"
                ]
            ),
            "logical_root_reference": (
                {
                    "root_kind": "PROFILE_CONDITIONING_PROGRAM",
                    "root_id": profile_program_id,
                }
                if profile_program_id is not None
                else {
                    "root_kind": (
                        "LOGICAL_PLAN_TEMPLATE"
                        if template_id is not None
                        else "LOCAL_SHUTDOWN_ANALYTIC_CATALOG"
                    ),
                    "root_id": (
                        template_id
                        if template_id is not None
                        else recurrence["local_shutdown_analytic_catalog"][
                            "local_shutdown_analytic_catalog_id"
                        ]
                    ),
                }
            ),
            "scope_summary": scope_summary,
            "root_step_position": (
                None
                if template_id is None
                else next(
                    row["root_step_position"]
                    for row in templates
                    if row["logical_plan_template_id"] == template_id
                )
            ),
        }
        logical_count_plan = {
            **plan_payload,
            "logical_count_plan_id": _semantic_id(
                _identity_domain(identity_records, "LOGICAL_COUNT_PLAN"),
                plan_payload,
            ),
        }
        logical_count_plan_records.append(logical_count_plan)
        case_plan_bindings.append(
            {
                "case_position": position,
                "logical_count_plan_position": position,
                "logical_count_plan_id": logical_count_plan["logical_count_plan_id"],
            }
        )
    _require(total_internal_scope_cases == 475, "contextual subcase total differs")
    _require(total_synthetic_axes == 33, "contextual synthetic-axis total differs")
    payload = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.logical_plan_recipe_catalog.v3"
        ),
        "logical_plan_schema": {
            "version": "riskyieldmm.raw_v8_step2_external_schema_v2.logical_count_plan.v3",
            "ordered_member_names": [
                "logical_count_plan_version",
                "case_position",
                "case_kind",
                "case_binding",
                "upper_bound_mode",
                "recurrence_catalog_id",
                "ordered_safe_relaxation_rule_ids",
                "logical_plan_template_id",
                "profile_conditioning_program_id",
                "local_analytic_catalog_id",
                "logical_root_reference",
                "scope_summary",
                "root_step_position",
                "logical_count_plan_id",
            ],
            "phase_invariant_excluded_member_names": [
                "maximum_protocol_sha256",
                "derivation_scope_id",
                "physical_derivation_plan_id",
                "physical_derivation_step_id",
            ],
            "compact_scope_summary_schema": {
                "ordered_member_names": [
                    "scope_summary_version",
                    *_SCOPE_SUMMARY_COUNT_MEMBERS,
                    "schedule_authority_kind",
                    "schedule_authority_id",
                    "application_schedule_operation_position",
                    "p2_cross_application_deletion_policy_id",
                ],
                "schedule_authority_kind_enum": [
                    "NONE",
                    "PROFILE_CONDITIONING_PROGRAM",
                    "LOCAL_SHUTDOWN_ANALYTIC_CATALOG",
                ],
                "expanded_schedule_storage_policy": (
                    "FORBIDDEN_IN_PLAN_RECONSTRUCT_FROM_IDENTITY_BOUND_AUTHORITY"
                ),
                "unknown_or_extra_member_policy": "REJECT",
            },
        },
        "case_plan_binding_schema": {
            "version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "case_plan_binding_reference.v1"
            ),
            "ordered_member_names": [
                "case_position",
                "logical_count_plan_position",
                "logical_count_plan_id",
            ],
            "position_rule": (
                "CASE_POSITION_EQUALS_LOGICAL_COUNT_PLAN_POSITION_"
                "AND_BOTH_ARE_CONTIGUOUS_ONE_BASED"
            ),
            "resolution_rule": (
                "RESOLVE_EXACT_ORDERED_LOGICAL_COUNT_PLAN_RECORD_BY_POSITION_"
                "THEN_REQUIRE_SEMANTIC_ID_EQUALITY"
            ),
            "unknown_or_extra_member_policy": "REJECT",
        },
        "logical_step_schema": {
            "version": "riskyieldmm.raw_v8_step2_external_schema_v2.logical_derivation_step.v1",
            "ordered_member_names": [
                "template_step_position",
                "derivation_kind",
                "subject_locator",
                "value_schema_id",
                "type_name",
                "alternative_name",
                "ordered_child_step_positions",
                "recurrence_parameters",
                "logical_descriptor_occurrence_count",
                "logical_transfer_multiplicity",
                "physical_transition_count",
                "logical_unbatched_transition_equivalent_count",
                "physical_batch_application_count",
                "ordered_intrinsic_rule_ids",
                "kernel_record_sha256",
                "state_signature_id",
                "cache_key_schema_version",
                "batch_equivalence_id",
                "logical_derivation_step_id",
            ],
        },
        "profile_conditioned_cell_contract": cell_contract,
        "p2_cross_application_deletion_policy": deletion_policy,
        "profile_conditioning_program_schema": {
            "version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "profile_conditioning_program.v1"
            ),
            "ordered_member_names": [
                "profile_conditioning_program_version",
                "program_position",
                "case_position",
                "profile_position",
                "maximum_constraint_scope_profile_id",
                "profile_inventory_json_pointer",
                "profile_kind",
                "constraint_scope",
                "operation_kind",
                "conditioning_strategy",
                "measured_type_name",
                "logical_plan_template_id",
                "template_root_step_position",
                "ordered_fixed_authority_operations",
                "scope_root_operation",
                "application_schedule_operation",
                "conditioning_transfer_program",
                "profile_conditioning_program_id",
            ],
            "ordered_operation_opcodes": [
                "FIXED_VALUE",
                "SCOPE_ROOT",
                "APPLICATION_SCHEDULE_COUNT",
            ],
            "fixed_authority_member_names": [
                "operation_position",
                "opcode",
                "inventory_json_pointer",
                "identity_member_name",
                "expected_authority_id",
                "fixed_canonical_octets",
                "fixed_canonical_sha256",
            ],
            "scope_case_member_names": [
                "scope_case_position",
                "root_family_position",
                "mode_attempt_pair_position",
                "observation_role_position",
                "measured_sequence_ordinal",
            ],
            "invocation_ordinal_program_enum": [
                "SINGLE_ZERO_NULL_BOUND_V1",
                "ZERO_BASED_OBSERVATION_RANGE_V1",
            ],
            "profile_strategy_enum": [
                "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1",
                "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
            ],
            "cross_application_relaxation_contract": {
                "generic_profile_policy": (
                    "PERMITTED_ONLY_WHEN_EVERY_SCHEDULED_CROSS_APPLICATION_IS_"
                    "BIJECTIVELY_MAPPED_TO_THE_IDENTITY_BOUND_DELETION_POLICY"
                ),
                "local_shutdown_profile_position_3_policy": "FORBIDDEN",
                "p1_p3_policy": "EXACT_APPLICATION_NO_RELAXATION",
            },
            "conditioning_transfer_program_schema": {
                "version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2."
                    "profile_conditioning_dual_channel_program.v1"
                ),
                "ordered_member_names": [
                    "program_version",
                    "cell_contract_id",
                    "p2_upper_bound_program",
                    "p1_p3_attainment_program",
                ],
                "p2_upper_bound_program_member_names": [
                    "program_version",
                    "upper_bound_source",
                    "ordered_safe_relaxation_rule_ids",
                    "ordered_template_relaxation_application_record_positions",
                    "p2_cross_application_deletion_policy_id",
                    "application_schedule_operation_position",
                    "ordered_deleted_cross_application_references",
                    "ordered_instruction_records",
                    "root_instruction_position",
                    "failure_policy",
                    "generic_attainability_claimed",
                ],
                "p1_p3_attainment_program_member_names": [
                    "program_version",
                    "ordered_instruction_records",
                    "root_instruction_position",
                    "failure_policy",
                ],
                "instruction_member_names": [
                    "instruction_position",
                    "opcode",
                    "ordered_input_instruction_positions",
                    "output_type",
                    "parameters",
                ],
                "deleted_cross_application_reference_member_names": [
                    "deletion_position",
                    "application_schedule_position",
                    "rule_application_id",
                ],
                "p2_opcode_enum": [
                    "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
                    "LOAD_FIXED_AUTHORITY_SET_V1",
                    "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
                    "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
                ],
                "p1_p3_opcode_enum": [
                    "IMPORT_P2_BOUND_CELL_V1",
                    "LOAD_RETAINED_WITNESS_CONTEXT_V1",
                    "LOAD_FIXED_AUTHORITY_SET_V1",
                    "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
                    "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
                    "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1",
                    "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
                    "REQUIRE_P1_AND_P3_EQUALITY_V1",
                ],
            },
            "endpoint_acceptance": (
                "P1_TRUE_AND_RETAINED_WITNESS_CANONICAL_LENGTH_EQUALS_P2_UPPER"
            ),
        },
        "logical_plan_instantiation_rule": {
            "rule_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "logical_plan_instantiation_rule.v1"
            ),
            "case_source": "ORDERED_CASE_BINDING_SAME_POSITION",
            "plan_source": ("ORDERED_LOGICAL_COUNT_PLAN_RECORD_SAME_POSITION_AND_ID"),
            "template_source": "LOGICAL_PLAN_TEMPLATE_ID_OR_NULL_FOR_CASE_475",
            "profile_conditioning_source": (
                "DUAL_CHANNEL_PROFILE_PROGRAM_REQUIRED_FOR_CASES_67_THROUGH_474"
            ),
            "scope_source": (
                "V4_PROFILE_REDERIVATION_MATCHES_COMPACT_COUNTS_AND_"
                "IDENTITY_BOUND_SCHEDULE_AUTHORITY_REFERENCE"
            ),
            "identity_payload_source": "STORED_COMPLETE_LOGICAL_COUNT_PLAN_EXCLUDING_FINAL_ID",
            "validation_order": [
                "CASE_BINDING",
                "TEMPLATE_OR_LOCAL_KERNEL",
                "PROFILE_FIXED_AUTHORITIES_SCOPE_AND_APPLICATION_PROGRAM",
                "P2_STRUCTURAL_SUPERSET_OR_LOCAL_ANALYTIC_EXACT_PROGRAM",
                "P2_EXACT_RELAXATION_POLICY",
                "P1_P3_EXACT_RETAINED_ATTAINMENT_PROGRAM",
                "COMPACT_SCOPE_SUMMARY_AND_SCHEDULE_AUTHORITY",
                "SAFE_RELAXATION_LIST",
                "PLAN_IDENTITY",
            ],
        },
        "ordered_logical_plan_templates": templates,
        "ordered_profile_conditioning_program_records": profile_programs,
        "ordered_logical_count_plan_records": logical_count_plan_records,
        "ordered_case_plan_bindings": case_plan_bindings,
        "ordered_plan_recipe_records": [
            {
                "recipe_position": 1,
                "case_kind": "MAXIMUM_PUBLICATION_ROW",
                "traversal": "REGISTRY_DESCRIPTOR_DEPTH_FIRST_CHILD_EDGE_ORDER_POSTORDER",
                "strategy": (
                    "STRUCTURAL_P2_SUPERSET_WITH_IDENTITY_BOUND_RELAXATIONS_"
                    "AND_EXACT_P1_P3_RETAINED_ATTAINMENT"
                ),
                "array_partition": "OBSERVED_ORDINAL_SINGLETONS_AND_MAXIMAL_BYTE_IDENTICAL_GAPS",
                "root_must_be_last": True,
                "upper_bound_mode": "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
            },
            {
                "recipe_position": 2,
                "case_kind": "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY",
                "traversal": "FIXED_ELEVEN_FIELD_LEXICAL_FOLD",
                "strategy": "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP_V1",
                "array_partition": None,
                "root_must_be_last": True,
                "upper_bound_mode": "EXACT_LEGAL_DOMAIN",
            },
        ],
    }
    return {
        **payload,
        "logical_plan_recipe_catalog_id": _semantic_id(
            _identity_domain(identity_records, "LOGICAL_PLAN_RECIPE_CATALOG"), payload
        ),
    }


def _source_specs() -> tuple[_SourceSpec, ...]:
    rows = (
        (
            "V4_INVENTORY",
            INVENTORY_PATH,
            INVENTORY_OCTETS,
            INVENTORY_RAW_SHA256,
            INVENTORY_ID,
        ),
        (
            "STRUCTURAL_REGISTRY",
            STRUCTURAL_REGISTRY_PATH,
            STRUCTURAL_REGISTRY_OCTETS,
            STRUCTURAL_REGISTRY_RAW_SHA256,
            STRUCTURAL_REGISTRY_ID,
        ),
        (
            "RULE_LITERAL_AUTHORITY",
            RULE_LITERAL_PATH,
            RULE_LITERAL_OCTETS,
            RULE_LITERAL_RAW_SHA256,
            None,
        ),
        (
            "CASE_EVENT_GRAMMAR",
            CASE_EVENT_GRAMMAR_PATH,
            CASE_EVENT_GRAMMAR_OCTETS,
            CASE_EVENT_GRAMMAR_RAW_SHA256,
            None,
        ),
        (
            "CASE_EVENT_HAND_ORACLES",
            CASE_EVENT_HAND_ORACLES_PATH,
            CASE_EVENT_HAND_ORACLES_OCTETS,
            CASE_EVENT_HAND_ORACLES_RAW_SHA256,
            None,
        ),
        (
            "CELL_TRANSFER_RULE_CATALOG",
            CELL_TRANSFER_RULE_CATALOG_PATH,
            CELL_TRANSFER_RULE_CATALOG_OCTETS,
            CELL_TRANSFER_RULE_CATALOG_RAW_SHA256,
            None,
        ),
        *(
            (role, path, octets, digest, None)
            for role, path, octets, digest in NORMATIVE_DOCUMENT_SOURCES
        ),
    )
    specs = [
        _SourceSpec(
            role,
            path,
            octets,
            digest,
            semantic_id,
            (
                "ARRAY"
                if path == CASE_EVENT_HAND_ORACLES_PATH
                else "OBJECT"
                if path.suffix == ".json"
                else None
            ),
        )
        for role, path, octets, digest, semantic_id in rows
    ]
    for name, octets, digest in UNICODE_SOURCES:
        path = Path("scripts/tests/unicode_15_0_0") / name
        specs.append(
            _SourceSpec(
                f"UNICODE_15_0_0_{name}",
                path,
                octets,
                digest,
                None,
                None,
            )
        )
    return tuple(specs)


def _authority_bindings(
    snapshots: dict[Path, _SourceSnapshot],
) -> list[dict[str, Any]]:
    return [
        {
            "authority_position": position,
            "authority_role": snapshot.spec.role,
            "repository_relative_path": path.as_posix(),
            "raw_octet_count": snapshot.spec.exact_octets,
            "raw_sha256": snapshot.spec.raw_sha256,
            "semantic_id": snapshot.spec.semantic_id,
        }
        for position, (path, snapshot) in enumerate(snapshots.items(), 1)
    ]


def _build_catalog_from_snapshots(
    snapshots: dict[Path, _SourceSnapshot],
) -> dict[str, Any]:
    authority_bindings = _authority_bindings(snapshots)
    parsed_json = {
        path: _parse_strict_canonical_json(
            snapshot.raw,
            label=snapshot.spec.role,
            root_kind=snapshot.spec.json_root_kind,
        )
        for path, snapshot in snapshots.items()
        if snapshot.spec.json_root_kind is not None
    }
    inventory = parsed_json[INVENTORY_PATH]
    _require(inventory.get("inventory_sha256") == INVENTORY_ID, "inventory ID differs")
    registry = inventory["external_schema_registry_v2"]
    _require(
        registry["external_schema_registry_id"] == STRUCTURAL_REGISTRY_ID,
        "registry ID differs",
    )
    separate_registry = parsed_json[STRUCTURAL_REGISTRY_PATH]
    _require(
        _canonical_bytes(registry) == _canonical_bytes(separate_registry),
        "embedded/separate registry differs",
    )

    identity_records = _identity_records()
    normative_records = inventory["normative_document_inputs"]
    expected_normative_records = [
        {
            "document_role": role,
            "repository_relative_path": path.as_posix(),
            "raw_octet_count": octets,
            "raw_sha256": digest,
        }
        for role, path, octets, digest in NORMATIVE_DOCUMENT_SOURCES
    ]
    _require(
        normative_records == expected_normative_records,
        "V4 normative-document authority order or pins differ",
    )

    identity_records = _identity_records()
    unicode_manifest = _unicode_manifest(identity_records, registry)
    f0 = _f0_catalog(identity_records)
    metrics = _metric_catalog(identity_records)
    transfer_rule_catalog = _validated_transfer_rule_catalog(
        snapshots[CELL_TRANSFER_RULE_CATALOG_PATH].raw, identity_records
    )
    recurrence = _recurrence_catalog(identity_records, inventory, transfer_rule_catalog)
    case_event_grammar = _validated_case_event_grammar(
        snapshots[CASE_EVENT_GRAMMAR_PATH].raw
    )
    _validate_full_case_execution_program(case_event_grammar, recurrence)
    cases = _case_universe(identity_records, inventory)
    recipes = _plan_recipe_catalog(
        identity_records, recurrence, registry, inventory, cases
    )
    case_event_grammar["ordered_hand_oracle_records"] = (
        _validated_case_event_hand_oracles(
            snapshots[CASE_EVENT_HAND_ORACLES_PATH].raw,
            recipes["ordered_logical_count_plan_records"],
        )
    )
    events = _event_catalog(identity_records, case_event_grammar)
    semantics_payload = {
        "protocol_version": PROTOCOL_VERSION,
        "identity_envelope_version": IDENTITY_ENVELOPE_VERSION,
        "unicode_authority_manifest_id": unicode_manifest[
            "unicode_authority_manifest_id"
        ],
        "f0_seed_ceiling_catalog_id": f0["f0_seed_ceiling_catalog_id"],
        "resource_metric_catalog_id": metrics["resource_metric_catalog_id"],
        "recurrence_catalog_id": recurrence["recurrence_catalog_id"],
        "logical_event_catalog_id": events["logical_event_catalog_id"],
        "case_universe_catalog_id": cases["case_universe_catalog_id"],
        "logical_plan_recipe_catalog_id": recipes["logical_plan_recipe_catalog_id"],
    }
    root_payload = {
        "catalog_version": CATALOG_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "identity_envelope_version": IDENTITY_ENVELOPE_VERSION,
        "ordered_authority_binding_records": authority_bindings,
        "ordered_identity_domain_records": identity_records,
        "unicode_authority_manifest": unicode_manifest,
        "f0_seed_ceiling_catalog": f0,
        "resource_metric_catalog": metrics,
        "recurrence_catalog": recurrence,
        "logical_event_catalog": events,
        "case_universe_catalog": cases,
        "logical_plan_recipe_catalog": recipes,
        "protocol_counting_semantics_id": _semantic_id(
            _identity_domain(identity_records, "PROTOCOL_COUNTING_SEMANTICS"),
            semantics_payload,
        ),
    }
    return {
        **root_payload,
        "seed_catalog_id": _semantic_id(
            _identity_domain(identity_records, "SEED_CATALOG"), root_payload
        ),
    }


def build_catalog(root: Path) -> dict[str, Any]:
    resolved_root = root.resolve(strict=True)
    specs = _source_specs()
    snapshots = _load_repeatable_source_snapshots(resolved_root, specs)
    return _build_catalog_from_snapshots(snapshots)


def _protected_inodes(
    snapshots: dict[Path, _SourceSnapshot],
) -> frozenset[tuple[int, int]]:
    return frozenset(snapshot.identity[:2] for snapshot in snapshots.values())


def _output_entry_identity(
    parent_descriptor: int, leaf_name: str
) -> tuple[int, int, int, int, int, int, int] | None:
    try:
        metadata = os.stat(leaf_name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    _require(stat.S_ISREG(metadata.st_mode), "existing output is not a regular file")
    _require(metadata.st_nlink == 1, "existing output is not single-link")
    return _file_identity(metadata)


def _atomic_write_repository_output(
    root: Path,
    relative_path: Path,
    rendered: bytes,
    *,
    protected_inodes: frozenset[tuple[int, int]],
) -> None:
    _require(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_NONBLOCK"),
        "platform lacks mandatory secure-output flags",
    )
    parts = _repository_relative_parts(relative_path)
    parent = _open_repository_directory_fd(root, parts[:-1], label="catalog output")
    parent_identity = _directory_identity(parent)
    leaf_name = parts[-1]
    temporary_name: str | None = None
    temporary_descriptor: int | None = None
    temporary_inode: tuple[int, int] | None = None
    renamed = False
    try:
        original_identity = _output_entry_identity(parent, leaf_name)
        if original_identity is not None:
            _require(
                original_identity[:2] not in protected_inodes,
                "existing output aliases a protected input inode",
            )
        flags = os.O_RDWR | os.O_NONBLOCK | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        for _ in range(32):
            candidate = f".{leaf_name}.tmp.{os.getpid()}.{secrets.token_hex(16)}"
            try:
                temporary_descriptor = os.open(candidate, flags, 0o600, dir_fd=parent)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        _require(
            temporary_descriptor is not None and temporary_name is not None,
            "cannot allocate a unique atomic output temporary",
        )
        offset = 0
        while offset < len(rendered):
            written = os.write(temporary_descriptor, rendered[offset:])
            _require(written > 0, "atomic output write made no progress")
            offset += written
        os.fchmod(temporary_descriptor, 0o644)
        os.fsync(temporary_descriptor)
        metadata = os.fstat(temporary_descriptor)
        _require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_nlink == 1
            and metadata.st_size == len(rendered),
            "atomic output temporary metadata differs",
        )
        temporary_inode = metadata.st_dev, metadata.st_ino
        _require(
            temporary_inode not in protected_inodes,
            "atomic output temporary aliases a protected input inode",
        )
        os.lseek(temporary_descriptor, 0, os.SEEK_SET)
        verified = bytearray()
        while len(verified) < len(rendered):
            chunk = os.read(
                temporary_descriptor,
                min(65_536, len(rendered) - len(verified)),
            )
            _require(bool(chunk), "atomic output temporary was truncated")
            verified.extend(chunk)
        _require(bytes(verified) == rendered, "atomic output temporary bytes differ")
        os.close(temporary_descriptor)
        temporary_descriptor = None
        _require(
            _output_entry_identity(parent, leaf_name) == original_identity,
            "output identity changed before atomic replacement",
        )
        _require(
            _current_directory_identity(root, parts[:-1], label="catalog output")
            == parent_identity,
            "output parent identity changed before replacement",
        )
        os.replace(
            temporary_name,
            leaf_name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
        )
        renamed = True
        os.fsync(parent)
        final_flags = os.O_RDONLY | os.O_NONBLOCK
        final_flags |= getattr(os, "O_CLOEXEC", 0)
        final_flags |= getattr(os, "O_NOFOLLOW", 0)
        final_descriptor = os.open(leaf_name, final_flags, dir_fd=parent)
        try:
            before = os.fstat(final_descriptor)
            _require(
                stat.S_ISREG(before.st_mode)
                and before.st_nlink == 1
                and before.st_size == len(rendered)
                and (before.st_dev, before.st_ino) == temporary_inode,
                "atomically published output metadata differs",
            )
            chunks: list[bytes] = []
            total = 0
            while total < len(rendered):
                chunk = os.read(final_descriptor, min(65_536, len(rendered) - total))
                _require(bool(chunk), "atomically published output was truncated")
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(final_descriptor)
            _require(
                _file_identity(before) == _file_identity(after)
                and b"".join(chunks) == rendered,
                "atomically published output bytes differ",
            )
            path_metadata = os.stat(leaf_name, dir_fd=parent, follow_symlinks=False)
            _require(
                _file_identity(path_metadata) == _file_identity(after),
                "atomically published output path identity changed",
            )
        finally:
            os.close(final_descriptor)
        _require(
            _current_directory_identity(root, parts[:-1], label="catalog output")
            == parent_identity,
            "output parent identity changed after replacement",
        )
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_name is not None and not renamed:
            try:
                os.unlink(temporary_name, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _secure_check_repository_output(
    root: Path,
    relative_path: Path,
    rendered: bytes,
    *,
    protected_inodes: frozenset[tuple[int, int]],
) -> None:
    snapshot = _bounded_repository_snapshot(
        root,
        _SourceSpec(
            "frozen seed catalog",
            relative_path,
            len(rendered),
            _sha256(rendered),
            None,
            "OBJECT",
        ),
    )
    _require(
        snapshot.identity[:2] not in protected_inodes,
        "frozen output aliases a protected input inode",
    )
    _require(snapshot.raw == rendered, "catalog is stale")
    _parse_strict_canonical_json(
        snapshot.raw, label="frozen seed catalog", root_kind="OBJECT"
    )


def _enforce_rendered_output(artifact: dict[str, Any], rendered: bytes) -> None:
    strict_limit = next(
        row["ceiling_value"]
        for row in artifact["f0_seed_ceiling_catalog"][
            "ordered_platform_ceiling_records"
        ]
        if row["resource_name"] == "INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"
    )
    _require(
        strict_limit == INDIVIDUAL_FILE_STRICT_UPPER_OCTETS,
        "catalog/code strict file ceilings differ",
    )
    _require(len(rendered) < strict_limit, "catalog reaches the strict F0 file cap")
    _require(
        len(rendered) <= OPERATIONAL_OUTPUT_MAXIMUM_OCTETS,
        "catalog exceeds the 15 MiB operational output target",
    )


def _repository_root(value: Path | None) -> Path:
    if value is not None:
        return value.resolve()
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()
    try:
        root = _repository_root(args.repository_root).resolve(strict=True)
        specs = _source_specs()
        snapshots = _load_repeatable_source_snapshots(root, specs)
        protected = _protected_inodes(snapshots)
        artifact = _build_catalog_from_snapshots(snapshots)
        raw = _pretty_bytes(artifact)
        _enforce_rendered_output(artifact, raw)
        current_sources = _snapshot_all_sources(root, specs)
        _assert_snapshot_sets_equal(snapshots, current_sources)
        if args.write:
            _atomic_write_repository_output(
                root, OUTPUT_PATH, raw, protected_inodes=protected
            )
            operation = "wrote"
        else:
            _secure_check_repository_output(
                root, OUTPUT_PATH, raw, protected_inodes=protected
            )
            operation = "checked"
        final_sources = _snapshot_all_sources(root, specs)
        _assert_snapshot_sets_equal(snapshots, final_sources)
        print(
            f"{operation} {OUTPUT_PATH} ({len(raw)} bytes, "
            f"raw_sha256={_sha256(raw)}, seed_catalog_id={artifact['seed_catalog_id']})"
        )
        return 0
    except (CatalogFailure, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(
            f"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_SEED_CATALOG_INVALID: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
