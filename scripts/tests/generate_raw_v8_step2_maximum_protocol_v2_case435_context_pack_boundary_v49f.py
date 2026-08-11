#!/usr/bin/env python3
"""Generate the additive case-435 packed-context boundary correction.

The accepted case-435 successor retains the predecessor candidate transport,
which assigns one physical file to every non-inline context object.  That is
not executable under F0: 38 successor authorities plus candidate.json leave
25 file slots, while the case-435 root application needs 67 distinct context
objects (the root and 66 non-inline observations).

This correction changes transport only.  It adds one compact canonical pack
file containing the complete logical context records.  It does not alter the
effective seed, manifest, plan, exact maximum, F2 ceilings, record-reference
identities, or verified publication format.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import secrets
import sys
from typing import Any, Final


class ContextPackBoundaryError(ValueError):
    """Raised when the transport correction cannot be reproduced exactly."""


ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
SUCCESSOR_BOUNDARY_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
OUTPUT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)

SEED_OCTETS: Final = 13_419_905
SEED_SHA256: Final = (
    "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
)
SEED_ID: Final = (
    "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
)
SUCCESSOR_BOUNDARY_OCTETS: Final = 4_806
SUCCESSOR_BOUNDARY_SHA256: Final = (
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c"
)
SUCCESSOR_BOUNDARY_ID: Final = (
    "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
)
SUCCESSOR_SEED_ID: Final = (
    "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
)
SUCCESSOR_MANIFEST_ID: Final = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
SUCCESSOR_PROTOCOL_SHA256: Final = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
SUCCESSOR_F2_ID: Final = (
    "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
)
SUCCESSOR_PROGRAM_ID: Final = (
    "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
)
SUCCESSOR_PLAN_ID: Final = (
    "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
)
EXACTNESS_JOIN_ID: Final = (
    "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
)

CASE_POSITION: Final = 435
MEASURED_SEQUENCE_ORDINAL: Final = 64
OBSERVATION_COUNT: Final = 67
INLINE_WITNESS_COUNT: Final = 1
NON_INLINE_OBSERVATION_COUNT: Final = 66
ROOT_CONTEXT_OBJECT_COUNT: Final = 1
LOGICAL_CONTEXT_OBJECT_COUNT: Final = 67
SUCCESSOR_AUTHORITY_FILE_COUNT: Final = 38

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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContextPackBoundaryError(message)


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


def _read_pinned_json(
    root: pathlib.Path, relative_path: str, octets: int, digest: str
) -> tuple[bytes, dict[str, Any]]:
    raw = (root / relative_path).read_bytes()
    _require(len(raw) == octets, f"pinned size differs: {relative_path}")
    _require(_sha256(raw) == digest, f"pinned hash differs: {relative_path}")
    value = json.loads(raw)
    _require(isinstance(value, dict), f"pinned JSON is not an object: {relative_path}")
    return raw, value


def build(root: pathlib.Path | str = ROOT) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    _seed_raw, seed = _read_pinned_json(root, SEED_PATH, SEED_OCTETS, SEED_SHA256)
    successor_raw, successor = _read_pinned_json(
        root,
        SUCCESSOR_BOUNDARY_PATH,
        SUCCESSOR_BOUNDARY_OCTETS,
        SUCCESSOR_BOUNDARY_SHA256,
    )
    _require(seed.get("seed_catalog_id") == SEED_ID, "predecessor seed ID differs")
    _require(
        successor.get("successor_constructive_boundary_id") == SUCCESSOR_BOUNDARY_ID,
        "successor boundary ID differs",
    )

    ceilings = {
        row["resource_name"]: row["ceiling_value"]
        for row in seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    }
    file_limit = ceilings["INPUT_FILE_COUNT"]
    individual_limit = ceilings["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
    total_limit = ceilings["TOTAL_PINNED_INPUT_OCTETS"]
    flat_file_count = (
        SUCCESSOR_AUTHORITY_FILE_COUNT + 1 + LOGICAL_CONTEXT_OBJECT_COUNT
    )
    packed_file_count = SUCCESSOR_AUTHORITY_FILE_COUNT + 1 + 1 + 1
    _require(
        file_limit == 64
        and individual_limit == 16_777_216
        and total_limit == 67_108_864,
        "F0 ceilings differ",
    )
    _require(flat_file_count > file_limit, "flat transport is not falsified")
    _require(packed_file_count <= file_limit, "packed transport cannot fit F0")

    value: dict[str, Any] = {
        "correction_version": CORRECTION_VERSION,
        "case_position": CASE_POSITION,
        "predecessor_successor_boundary_authority": {
            "repository_relative_path": SUCCESSOR_BOUNDARY_PATH,
            "raw_octets": len(successor_raw),
            "raw_sha256": _sha256(successor_raw),
            "successor_constructive_boundary_id": SUCCESSOR_BOUNDARY_ID,
        },
        "unchanged_effective_authorities": {
            "successor_seed_catalog_id": SUCCESSOR_SEED_ID,
            "successor_manifest_id": SUCCESSOR_MANIFEST_ID,
            "maximum_protocol_sha256": SUCCESSOR_PROTOCOL_SHA256,
            "f2_resource_limit_catalog_id": SUCCESSOR_F2_ID,
            "case435_profile_conditioning_program_id": SUCCESSOR_PROGRAM_ID,
            "case435_logical_count_plan_id": SUCCESSOR_PLAN_ID,
            "case435_exactness_join_certificate_id": EXACTNESS_JOIN_ID,
            "case435_exact_maximum_octets": 257_887,
        },
        "f0_contradiction_proof": {
            "input_file_count_ceiling": file_limit,
            "successor_authority_file_count_before_this_delta": SUCCESSOR_AUTHORITY_FILE_COUNT,
            "candidate_envelope_file_count": 1,
            "observation_count": OBSERVATION_COUNT,
            "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "inline_witness_count": INLINE_WITNESS_COUNT,
            "non_inline_observation_context_object_count": NON_INLINE_OBSERVATION_COUNT,
            "root_context_object_count": ROOT_CONTEXT_OBJECT_COUNT,
            "logical_context_object_count": LOGICAL_CONTEXT_OBJECT_COUNT,
            "minimum_flat_input_file_count": flat_file_count,
            "flat_transport_acceptance_state": "IMPOSSIBLE_UNDER_IMMUTABLE_F0",
        },
        "packed_context_candidate_contract": {
            "candidate_version_literal": PACKED_CANDIDATE_VERSION,
            "candidate_identity_domain": PACKED_CANDIDATE_DOMAIN,
            "candidate_kind": "MAXIMUM_WITNESS_PACKED_CONTEXT",
            "ordered_payload_member_names": [
                "candidate_kind",
                "witness_record",
                "scope_witness_context",
                "ordered_context_pack_entries",
            ],
            "required_case_position": CASE_POSITION,
            "required_context_kind": "ROOT_APPLICATION",
            "required_measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "required_observation_reference_count": OBSERVATION_COUNT,
            "required_inline_witness_reference_count": INLINE_WITNESS_COUNT,
            "required_logical_context_object_count": LOGICAL_CONTEXT_OBJECT_COUNT,
            "unknown_or_extra_member_policy": "REJECT",
        },
        "context_pack_contract": {
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
            "required_context_object_count_for_case435": LOGICAL_CONTEXT_OBJECT_COUNT,
            "context_object_ordering_rule": "STRICTLY_INCREASING_MAXIMUM_CONTEXT_OBJECT_ID",
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
            "individual_pack_strict_upper_octets": individual_limit,
            "unknown_duplicate_missing_extra_or_overlapping_record_policy": "REJECT",
        },
        "filesystem_and_publication_contract": {
            "candidate_pack_snapshot_rule": (
                "PIN_PATH_DEVICE_INODE_SIZE_MODE_MTIME_CTIME_AND_BYTES_THEN_RECHECK"
            ),
            "symlink_hardlink_fifo_device_socket_policy": "REJECT",
            "bounded_read_rule": "FSTAT_EXACT_LIMITED_READ_REQUIRE_EOF_FSTAT_RECHECK",
            "input_pack_count": 1,
            "corrected_minimum_input_file_count": packed_file_count,
            "input_file_count_headroom": file_limit - packed_file_count,
            "total_pinned_input_octet_ceiling": total_limit,
            "verified_output_rule": (
                "UNPACK_TO_INHERITED_COMPACT_CONTEXT_OBJECT_FILES_AND_INHERITED_"
                "LOGICAL_RECEIPT_ENTRIES"
            ),
            "context_object_semantic_id_domain_unchanged": True,
            "record_reference_semantic_id_domain_unchanged": True,
        },
        "scope_and_non_drift_contract": {
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
    }
    value["case435_context_pack_boundary_delta_id"] = _domain_id(
        CORRECTION_DOMAIN, value
    )
    return value


def _write_atomic(path: pathlib.Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            _require(written > 0, "output write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", nargs="?", default=str(ROOT))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.repository_root).resolve()
    raw = _pretty_bytes(build(root))
    output = root / OUTPUT_PATH
    if arguments.check:
        _require(output.is_file(), "published context-pack boundary is absent")
        _require(output.read_bytes() == raw, "published context-pack boundary is stale")
        return 0
    _write_atomic(output, raw)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContextPackBoundaryError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"CASE435_CONTEXT_PACK_BOUNDARY_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from error
