#!/usr/bin/env python3
"""Independently verify the case-435 packed-context boundary correction."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any, Final


class ContextPackBoundaryReject(ValueError):
    """Raised when the packed-context correction is not exact and closed."""


ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
SUCCESSOR_BOUNDARY_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
CORRECTION_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)

SEED_PIN: Final = (
    13_419_905,
    "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f",
)
SUCCESSOR_BOUNDARY_PIN: Final = (
    4_806,
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c",
    "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d",
)
CORRECTION_PIN: Final = (
    6_049,
    "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd",
)

CORRECTION_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "case435_context_pack_boundary_delta.v1"
)
CORRECTION_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ContextPackBoundaryDeltaV1V4_9F_RawV8"
)
PACK_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.case435_context_pack.v1"
)
PACK_DOMAIN: Final = (
    "RiskYieldMMStep2Case435ContextPackV1V4_9F_RawV8"
)
PACKED_CANDIDATE_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "constructive_candidate_envelope.case435_packed_context.v1"
)
PACKED_CANDIDATE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2Case435PackedContextCandidateV1V4_9F_RawV8"
)

TOP_MEMBERS: Final = {
    "correction_version",
    "case_position",
    "predecessor_successor_boundary_authority",
    "unchanged_effective_authorities",
    "f0_contradiction_proof",
    "packed_context_candidate_contract",
    "context_pack_contract",
    "filesystem_and_publication_contract",
    "scope_and_non_drift_contract",
    "case435_context_pack_boundary_delta_id",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContextPackBoundaryReject(message)


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


def _read(
    root: pathlib.Path,
    path: str,
    pin: tuple[int, str, str],
    identity_name: str,
) -> tuple[bytes, dict[str, Any]]:
    raw = (root / path).read_bytes()
    _require(len(raw) == pin[0], f"raw size differs: {path}")
    _require(_sha256(raw) == pin[1], f"raw hash differs: {path}")
    value = json.loads(raw)
    _require(isinstance(value, dict), f"authority is not an object: {path}")
    _require(raw == _pretty_bytes(value), f"authority encoding differs: {path}")
    _require(value.get(identity_name) == pin[2], f"semantic ID differs: {path}")
    return raw, value


def _closed(value: Any, names: set[str], label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} is not an object")
    _require(set(value) == names, f"{label} members differ")
    return value


def verify(root: pathlib.Path | str = ROOT) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    _seed_raw, seed = _read(root, SEED_PATH, SEED_PIN, "seed_catalog_id")
    successor_raw, successor = _read(
        root,
        SUCCESSOR_BOUNDARY_PATH,
        SUCCESSOR_BOUNDARY_PIN,
        "successor_constructive_boundary_id",
    )
    correction_raw, correction = _read(
        root,
        CORRECTION_PATH,
        CORRECTION_PIN,
        "case435_context_pack_boundary_delta_id",
    )
    _closed(correction, TOP_MEMBERS, "correction")
    payload = {
        name: value
        for name, value in correction.items()
        if name != "case435_context_pack_boundary_delta_id"
    }
    _require(
        correction["case435_context_pack_boundary_delta_id"]
        == _domain_id(CORRECTION_DOMAIN, payload),
        "correction semantic ID does not reproduce",
    )
    _require(
        correction["correction_version"] == CORRECTION_VERSION
        and correction["case_position"] == 435,
        "correction version/case differs",
    )

    predecessor = _closed(
        correction["predecessor_successor_boundary_authority"],
        {
            "repository_relative_path",
            "raw_octets",
            "raw_sha256",
            "successor_constructive_boundary_id",
        },
        "predecessor successor boundary",
    )
    _require(
        predecessor
        == {
            "repository_relative_path": SUCCESSOR_BOUNDARY_PATH,
            "raw_octets": len(successor_raw),
            "raw_sha256": _sha256(successor_raw),
            "successor_constructive_boundary_id": SUCCESSOR_BOUNDARY_PIN[2],
        },
        "predecessor successor-boundary binding differs",
    )

    unchanged = _closed(
        correction["unchanged_effective_authorities"],
        {
            "successor_seed_catalog_id",
            "successor_manifest_id",
            "maximum_protocol_sha256",
            "f2_resource_limit_catalog_id",
            "case435_profile_conditioning_program_id",
            "case435_logical_count_plan_id",
            "case435_exactness_join_certificate_id",
            "case435_exact_maximum_octets",
        },
        "unchanged effective authorities",
    )
    _require(
        unchanged
        == {
            "successor_seed_catalog_id": "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b",
            "successor_manifest_id": "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c",
            "maximum_protocol_sha256": "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf",
            "f2_resource_limit_catalog_id": "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f",
            "case435_profile_conditioning_program_id": "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820",
            "case435_logical_count_plan_id": "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8",
            "case435_exactness_join_certificate_id": "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f",
            "case435_exact_maximum_octets": 257_887,
        },
        "effective mathematical authority drifted",
    )
    _require(
        successor["successor_f2_resource_limit_catalog"][
            "f2_resource_limit_catalog_id"
        ]
        == unchanged["f2_resource_limit_catalog_id"],
        "correction does not preserve successor F2 identity",
    )

    ceilings = {
        row["resource_name"]: row["ceiling_value"]
        for row in seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    }
    contradiction = _closed(
        correction["f0_contradiction_proof"],
        {
            "input_file_count_ceiling",
            "successor_authority_file_count_before_this_delta",
            "candidate_envelope_file_count",
            "observation_count",
            "measured_sequence_ordinal",
            "inline_witness_count",
            "non_inline_observation_context_object_count",
            "root_context_object_count",
            "logical_context_object_count",
            "minimum_flat_input_file_count",
            "flat_transport_acceptance_state",
        },
        "F0 contradiction proof",
    )
    _require(
        contradiction["input_file_count_ceiling"] == ceilings["INPUT_FILE_COUNT"] == 64
        and contradiction["successor_authority_file_count_before_this_delta"] == 38
        and contradiction["candidate_envelope_file_count"] == 1
        and contradiction["observation_count"] == 67
        and contradiction["measured_sequence_ordinal"] == 64
        and contradiction["inline_witness_count"] == 1
        and contradiction["non_inline_observation_context_object_count"] == 66
        and contradiction["root_context_object_count"] == 1
        and contradiction["logical_context_object_count"] == 67
        and contradiction["minimum_flat_input_file_count"] == 38 + 1 + 67 == 106
        and contradiction["minimum_flat_input_file_count"]
        > contradiction["input_file_count_ceiling"]
        and contradiction["flat_transport_acceptance_state"]
        == "IMPOSSIBLE_UNDER_IMMUTABLE_F0",
        "F0 contradiction arithmetic differs",
    )
    pilot = successor["case435_pilot_record_override"]
    _require(
        pilot["case_position"] == 435
        and pilot["coverage_tag"]
        == "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887",
        "successor does not require the full case435 context",
    )

    candidate = _closed(
        correction["packed_context_candidate_contract"],
        {
            "candidate_version_literal",
            "candidate_identity_domain",
            "candidate_kind",
            "ordered_payload_member_names",
            "required_case_position",
            "required_context_kind",
            "required_measured_sequence_ordinal",
            "required_observation_reference_count",
            "required_inline_witness_reference_count",
            "required_logical_context_object_count",
            "unknown_or_extra_member_policy",
        },
        "packed candidate contract",
    )
    _require(
        candidate["candidate_version_literal"] == PACKED_CANDIDATE_VERSION
        and candidate["candidate_identity_domain"] == PACKED_CANDIDATE_DOMAIN
        and candidate["candidate_kind"] == "MAXIMUM_WITNESS_PACKED_CONTEXT"
        and candidate["ordered_payload_member_names"]
        == [
            "candidate_kind",
            "witness_record",
            "scope_witness_context",
            "ordered_context_pack_entries",
        ]
        and candidate["required_case_position"] == 435
        and candidate["required_context_kind"] == "ROOT_APPLICATION"
        and candidate["required_measured_sequence_ordinal"] == 64
        and candidate["required_observation_reference_count"] == 67
        and candidate["required_inline_witness_reference_count"] == 1
        and candidate["required_logical_context_object_count"] == 67
        and candidate["unknown_or_extra_member_policy"] == "REJECT",
        "packed candidate contract differs",
    )

    pack = _closed(
        correction["context_pack_contract"],
        {
            "context_pack_version",
            "context_pack_identity_domain",
            "physical_encoding",
            "ordered_pack_member_names",
            "ordered_context_object_record_member_names",
            "ordered_candidate_pack_entry_member_names",
            "repository_relative_path_rule",
            "required_pack_count_for_case435",
            "required_context_object_count_for_case435",
            "context_object_ordering_rule",
            "logical_closure_rule",
            "inline_witness_exclusion_rule",
            "record_validation_rule",
            "individual_pack_strict_upper_octets",
            "unknown_duplicate_missing_extra_or_overlapping_record_policy",
        },
        "context pack contract",
    )
    expected_pack = {
        "context_pack_version": PACK_VERSION,
        "context_pack_identity_domain": PACK_DOMAIN,
        "physical_encoding": "EXACT_COMPACT_CANONICAL_UTF8_JSON_NO_TRAILING_BYTE",
        "ordered_pack_member_names": [
            "context_pack_version",
            "canonicalization_version",
            "measurement_schema_version",
            "maximum_protocol_sha256",
            "case_position",
            "pack_position",
            "ordered_context_object_records",
            "context_pack_id",
        ],
        "ordered_context_object_record_member_names": [
            "context_object_position",
            "maximum_context_object_id",
            "record_type_name",
            "record_identity_field",
            "record_identity",
            "record_canonical_byte_length",
            "record_canonical_sha256",
            "record",
        ],
        "ordered_candidate_pack_entry_member_names": [
            "context_pack_position",
            "context_pack_id",
            "first_maximum_context_object_id",
            "last_maximum_context_object_id",
            "context_object_count",
            "repository_relative_path",
            "raw_octet_count",
            "raw_sha256",
        ],
        "repository_relative_path_rule": (
            "context_objects/packs/<first-two-pack-id-characters>/"
            "<context-pack-id>.json"
        ),
        "required_pack_count_for_case435": 1,
        "required_context_object_count_for_case435": 67,
        "context_object_ordering_rule": (
            "STRICTLY_INCREASING_MAXIMUM_CONTEXT_OBJECT_ID"
        ),
        "logical_closure_rule": (
            "EVERY_AND_ONLY_CONTEXT_OBJECT_REFERENCE_REACHABLE_FROM_"
            "SCOPE_WITNESS_CONTEXT_RESOLVES_ONCE"
        ),
        "inline_witness_exclusion_rule": (
            "INLINE_WITNESS_RECORD_IS_NOT_DUPLICATED_IN_CONTEXT_PACK"
        ),
        "record_validation_rule": (
            "RECOMPUTE_COMPLETE_TYPED_RECORD_LEGALITY_IDENTITY_CANONICAL_"
            "LENGTH_HASH_AND_REFERENCE_BINDING"
        ),
        "individual_pack_strict_upper_octets": ceilings[
            "INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"
        ],
        "unknown_duplicate_missing_extra_or_overlapping_record_policy": "REJECT",
    }
    _require(
        pack == expected_pack
        and pack["individual_pack_strict_upper_octets"] == 16_777_216,
        "pack member order differs",
    )

    filesystem = _closed(
        correction["filesystem_and_publication_contract"],
        {
            "candidate_pack_snapshot_rule",
            "symlink_hardlink_fifo_device_socket_policy",
            "bounded_read_rule",
            "input_pack_count",
            "corrected_minimum_input_file_count",
            "input_file_count_headroom",
            "total_pinned_input_octet_ceiling",
            "verified_output_rule",
            "context_object_semantic_id_domain_unchanged",
            "record_reference_semantic_id_domain_unchanged",
        },
        "filesystem and publication contract",
    )
    _require(
        filesystem
        == {
            "candidate_pack_snapshot_rule": (
                "PIN_PATH_DEVICE_INODE_SIZE_MODE_MTIME_CTIME_AND_BYTES_THEN_RECHECK"
            ),
            "symlink_hardlink_fifo_device_socket_policy": "REJECT",
            "bounded_read_rule": (
                "FSTAT_EXACT_LIMITED_READ_REQUIRE_EOF_FSTAT_RECHECK"
            ),
            "input_pack_count": 1,
            "corrected_minimum_input_file_count": 41,
            "input_file_count_headroom": 23,
            "total_pinned_input_octet_ceiling": ceilings[
                "TOTAL_PINNED_INPUT_OCTETS"
            ],
            "verified_output_rule": (
                "UNPACK_TO_INHERITED_COMPACT_CONTEXT_OBJECT_FILES_AND_INHERITED_"
                "LOGICAL_RECEIPT_ENTRIES"
            ),
            "context_object_semantic_id_domain_unchanged": True,
            "record_reference_semantic_id_domain_unchanged": True,
        }
        and ceilings["TOTAL_PINNED_INPUT_OCTETS"] == 67_108_864,
        "packed filesystem/F0 proof differs",
    )
    nondrift = correction["scope_and_non_drift_contract"]
    _require(
        nondrift
        == {
            "authorized_change": "CASE435_CANDIDATE_CONTEXT_PHYSICAL_TRANSPORT_ONLY",
            "predecessor_and_successor_boundary_bytes_unchanged": True,
            "candidate_transport_for_cases_5_24_54_69_unchanged": True,
            "case475_transport_unchanged_and_unsupported_during_v3": True,
            "seed_manifest_plan_program_exactness_and_f2_values_unchanged": True,
            "f0_or_f2_limit_increase_forbidden": True,
            "c2_certificate_or_stored_witness_as_verifier_input_forbidden": True,
            "old_flat_case435_transport_acceptance_policy": "REJECT",
            "next_subgate": "A4-P6-V3",
        },
        "correction scope/non-drift contract differs",
    )

    return {
        "verification_status": "ACCEPTED",
        "case_position": 435,
        "case435_context_pack_boundary_delta_id": correction[
            "case435_context_pack_boundary_delta_id"
        ],
        "correction_raw_octets": len(correction_raw),
        "correction_raw_sha256": _sha256(correction_raw),
        "flat_minimum_input_file_count": contradiction[
            "minimum_flat_input_file_count"
        ],
        "packed_minimum_input_file_count": filesystem[
            "corrected_minimum_input_file_count"
        ],
        "packed_input_file_headroom": filesystem["input_file_count_headroom"],
        "logical_context_object_count": 67,
        "required_context_pack_count": 1,
        "individual_pack_strict_upper_octets": pack[
            "individual_pack_strict_upper_octets"
        ],
        "unchanged_case435_exact_maximum_octets": unchanged[
            "case435_exact_maximum_octets"
        ],
        "next_subgate": "A4-P6-V3",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        raise ContextPackBoundaryReject("expected at most one repository root")
    root = pathlib.Path(argv[0]).resolve() if argv else ROOT
    print(_canonical_bytes(verify(root)).decode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContextPackBoundaryReject, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"CASE435_CONTEXT_PACK_BOUNDARY_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from error
