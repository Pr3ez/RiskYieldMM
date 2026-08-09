#!/usr/bin/env python3
"""Independently validate the Raw-V8 Step-2 external-schema V2 foundation.

This validator uses only the Python standard library. It deliberately does not
import the inventory generator, ``riskyieldmm``, or any production source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Final

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
FOUNDATION_LEDGER_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.foundation_ledger.v1"
)
FOUNDATION_COMPONENT_STATUS: Final = "FOUNDATION_ONLY_NOT_EXTERNAL_SCHEMA_REGISTRY_V2"
FOUNDATION_LEDGER_SHA256: Final = (
    "fc2b888559067fddb5178a87bcae3ab4876e5c17fab766da6ce54581eeff34fb"
)
FOUNDATION_LEDGER_MAXIMUM_OCTETS: Final = 65_536
FOUNDATION_MAXIMUM_JSON_NESTING_DEPTH: Final = 16
SOURCE_DOMAIN: Final = "RiskYieldMMA2MStep2UnicodeSourceRecordV1V4_9F_RawV8"
PROFILE_DOMAIN: Final = "RiskYieldMMA2MStep2UnicodeIdentifierProfileV1V4_9F_RawV8"
SAFE_UINT_MAX: Final = 9_007_199_254_740_991
SOURCE_PAYLOAD_ORDER: Final = (
    "source_name",
    "unicode_version",
    "official_url",
    "byte_count",
    "sha256",
)
PROFILE_PAYLOAD_ORDER: Final = (
    "profile_id",
    "unicode_version",
    "normalization_form",
    "maximum_scalar_values",
    "maximum_utf8_octets",
    "forbidden_code_point_ranges",
    "edge_trim_code_points",
    "unicode_source_record_ids",
)
PROFILE_SPEC_ORDER: Final = (
    "profile_id",
    "unicode_version",
    "normalization_form",
    "maximum_scalar_values",
    "maximum_utf8_octets",
    "forbidden_code_point_ranges",
    "edge_trim_code_points",
    "unicode_source_names",
)
SURFACE_ASSIGNMENT_ORDER: Final = (
    "surface_position",
    "type_name",
    "typed_member_path",
    "value_location",
    "nullable",
    "profile_id",
)
EDGE_TRIM_CODE_POINTS: Final = (
    "U+0009",
    "U+000A",
    "U+000B",
    "U+000C",
    "U+000D",
    "U+001C",
    "U+001D",
    "U+001E",
    "U+001F",
    "U+0020",
    "U+0085",
    "U+00A0",
    "U+1680",
    "U+2000",
    "U+2001",
    "U+2002",
    "U+2003",
    "U+2004",
    "U+2005",
    "U+2006",
    "U+2007",
    "U+2008",
    "U+2009",
    "U+200A",
    "U+2028",
    "U+2029",
    "U+202F",
    "U+205F",
    "U+3000",
)
PROFILE_LIMITS: Final = {
    "RAW_V8_UNICODE_IDENTIFIER_A_V1": (128, 128, 5),
    "RAW_V8_UNICODE_IDENTIFIER_B_V1": (256, 256, 4),
    "RAW_V8_UNICODE_IDENTIFIER_C_V1": (256, 1_024, 1),
}
SOURCE_NAMES: Final = (
    "CompositionExclusions.txt",
    "DerivedNormalizationProps.txt",
    "NormalizationTest.txt",
    "PropList.txt",
    "ReadMe.txt",
    "UnicodeData.txt",
)


class FoundationValidationError(ValueError):
    """Raised when the independent foundation ledger is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FoundationValidationError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_pretty_bytes(value: Any) -> bytes:
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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    return _sha256_bytes(
        _canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": domain,
                "payload": payload,
                "schema_version": MEASUREMENT_SCHEMA_VERSION,
            }
        )
    )


def _reject_json_constant(value: str) -> Any:
    raise FoundationValidationError(
        f"foundation ledger contains non-finite JSON: {value}"
    )


def _reject_json_float(value: str) -> Any:
    raise FoundationValidationError(f"foundation ledger contains a float: {value}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FoundationValidationError(
                f"foundation ledger contains duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _validate_json_nesting(text: str) -> None:
    """Bound JSON nesting before decode while ignoring structure inside strings."""

    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            _require(
                depth <= FOUNDATION_MAXIMUM_JSON_NESTING_DEPTH,
                "foundation ledger JSON nesting exceeds the reviewed bound",
            )
        elif character in "]}":
            depth -= 1
            _require(
                depth >= 0,
                "foundation ledger JSON closes an unopened container",
            )
    _require(not in_string, "foundation ledger contains an unterminated JSON string")
    _require(depth == 0, "foundation ledger JSON has unclosed containers")


def _require_json_scalar_strings(value: Any) -> None:
    """Reject escaped lone surrogates in every decoded JSON key and value."""

    if type(value) is str:
        _require(
            not any(0xD800 <= ord(character) <= 0xDFFF for character in value),
            "foundation ledger contains a non-scalar JSON string",
        )
    elif type(value) is list:
        for item in value:
            _require_json_scalar_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            _require_json_scalar_strings(key)
            _require_json_scalar_strings(item)


def _exact_object(
    value: Any,
    member_order: tuple[str, ...],
    *,
    label: str,
) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} is not an exact object")
    _require(
        set(value) == set(member_order),
        f"{label} has missing or extra members",
    )
    return value


def _expected_metadata_shapes() -> dict[str, dict[str, Any]]:
    source_payload = list(SOURCE_PAYLOAD_ORDER)
    profile_payload = list(PROFILE_PAYLOAD_ORDER)
    surface_payload = list(SURFACE_ASSIGNMENT_ORDER)
    return {
        "identifier_profile": {
            "identity_field": "unicode_identifier_profile_id",
            "identity_payload_member_order": profile_payload,
            "materialized_member_order": [
                *profile_payload,
                "unicode_identifier_profile_id",
            ],
            "semantic_id_domain": PROFILE_DOMAIN,
            "source_spec_member_order": list(PROFILE_SPEC_ORDER),
        },
        "surface_assignment": {
            "identity_field": None,
            "identity_payload_member_order": None,
            "materialized_member_order": surface_payload,
            "semantic_id_domain": None,
            "source_spec_member_order": surface_payload,
        },
        "unicode_source": {
            "identity_field": "unicode_source_record_id",
            "identity_payload_member_order": source_payload,
            "materialized_member_order": [
                *source_payload,
                "unicode_source_record_id",
            ],
            "semantic_id_domain": SOURCE_DOMAIN,
            "source_spec_member_order": source_payload,
        },
    }


def _expected_source_specs() -> list[dict[str, Any]]:
    return [
        {
            "byte_count": 8_911,
            "official_url": (
                "https://www.unicode.org/Public/15.0.0/ucd/CompositionExclusions.txt"
            ),
            "sha256": (
                "3b019c0a33c3140cbc920c078f4f9af2680ba4f71869c8d4de5190667c70b6a3"
            ),
            "source_name": "CompositionExclusions.txt",
            "unicode_version": "15.0.0",
        },
        {
            "byte_count": 837_688,
            "official_url": (
                "https://www.unicode.org/Public/15.0.0/ucd/"
                "DerivedNormalizationProps.txt"
            ),
            "sha256": (
                "d5687a48c95c7d6e1ec59cb29c0f2e8b052018eb069a4371b7368d0561e12a29"
            ),
            "source_name": "DerivedNormalizationProps.txt",
            "unicode_version": "15.0.0",
        },
        {
            "byte_count": 2_625_136,
            "official_url": (
                "https://www.unicode.org/Public/15.0.0/ucd/NormalizationTest.txt"
            ),
            "sha256": (
                "fb9ac8cc154a80cad6caac9897af55a4e75176af6f4e2bb6edc2bf8b1d57f326"
            ),
            "source_name": "NormalizationTest.txt",
            "unicode_version": "15.0.0",
        },
        {
            "byte_count": 132_360,
            "official_url": ("https://www.unicode.org/Public/15.0.0/ucd/PropList.txt"),
            "sha256": (
                "e05c0a2811d113dae4abd832884199a3ea8d187ee1b872d8240a788a96540bfd"
            ),
            "source_name": "PropList.txt",
            "unicode_version": "15.0.0",
        },
        {
            "byte_count": 635,
            "official_url": ("https://www.unicode.org/Public/15.0.0/ucd/ReadMe.txt"),
            "sha256": (
                "53672c0d0b5185e3cf04c8e970d544c3af81ae7c8eeba0b9cf6d355aa954ae1f"
            ),
            "source_name": "ReadMe.txt",
            "unicode_version": "15.0.0",
        },
        {
            "byte_count": 1_913_704,
            "official_url": (
                "https://www.unicode.org/Public/15.0.0/ucd/UnicodeData.txt"
            ),
            "sha256": (
                "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73"
            ),
            "source_name": "UnicodeData.txt",
            "unicode_version": "15.0.0",
        },
    ]


def _expected_profile_specs() -> list[dict[str, Any]]:
    forbidden_ranges = [["U+0000", "U+001F"], ["U+007F", "U+007F"]]
    result: list[dict[str, Any]] = []
    for profile_id, (scalar_maximum, octet_maximum, _) in PROFILE_LIMITS.items():
        result.append(
            {
                "edge_trim_code_points": list(EDGE_TRIM_CODE_POINTS),
                "forbidden_code_point_ranges": forbidden_ranges,
                "maximum_scalar_values": scalar_maximum,
                "maximum_utf8_octets": octet_maximum,
                "normalization_form": "NFC",
                "profile_id": profile_id,
                "unicode_source_names": list(SOURCE_NAMES),
                "unicode_version": "15.0.0",
            }
        )
    return result


def _surface_assignment(
    position: int,
    type_name: str,
    member_name: str,
    profile_id: str,
    *,
    value_location: str = "MEMBER_VALUE",
    nullable: bool = False,
) -> dict[str, Any]:
    return {
        "nullable": nullable,
        "profile_id": profile_id,
        "surface_position": position,
        "type_name": type_name,
        "typed_member_path": [member_name],
        "value_location": value_location,
    }


def _expected_surface_assignments() -> list[dict[str, Any]]:
    profile_a = "RAW_V8_UNICODE_IDENTIFIER_A_V1"
    profile_b = "RAW_V8_UNICODE_IDENTIFIER_B_V1"
    profile_c = "RAW_V8_UNICODE_IDENTIFIER_C_V1"
    return [
        _surface_assignment(
            1,
            "CapacityMeasurementAckDeadlineExpirySpecV1",
            "workload_family",
            profile_a,
        ),
        _surface_assignment(
            2,
            "CapacityMeasurementIngressOperationSpecV2",
            "workload_family",
            profile_a,
        ),
        _surface_assignment(
            3,
            "CapacityMeasurementLocalShutdownSpecV2",
            "workload_family",
            profile_a,
        ),
        _surface_assignment(
            4,
            "CapacityMeasurementSubscriptionDispatchSpecV2",
            "workload_family",
            profile_a,
        ),
        _surface_assignment(
            5,
            "CapacityMeasurementOperationDeclarationV1",
            "stage",
            profile_a,
        ),
        _surface_assignment(
            6,
            "CapacityMeasurementOperationDeclarationV1",
            "workload_id",
            profile_b,
        ),
        _surface_assignment(
            7,
            "CapacityMeasurementTextValueV1",
            "value",
            profile_b,
        ),
        _surface_assignment(
            8,
            "CapacityMeasurementOptionalTextValueV1",
            "value",
            profile_b,
            nullable=True,
        ),
        _surface_assignment(
            9,
            "CapacityMeasurementTextListValueV1",
            "values",
            profile_b,
            value_location="ARRAY_ITEM_VALUE",
        ),
        _surface_assignment(
            10,
            "CapacityMeasurementSubscriptionDispatchSpecV2",
            "expected_topic",
            profile_c,
        ),
    ]


def _code_point(value: Any) -> int:
    _require(
        type(value) is str and re.fullmatch(r"U\+[0-9A-F]{4,6}", value) is not None,
        "foundation code point is not canonical U+ notation",
    )
    result = int(value[2:], 16)
    _require(
        result <= 0x10FFFF and not 0xD800 <= result <= 0xDFFF,
        "foundation code point is not a Unicode scalar value",
    )
    return result


def _load_ledger(path: Path) -> tuple[bytes, dict[str, Any]]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FoundationValidationError(
            f"cannot open foundation ledger: {exc}"
        ) from exc
    try:
        metadata_before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(metadata_before.st_mode),
            "foundation ledger is not a direct regular file",
        )
        _require(metadata_before.st_size > 0, "foundation ledger is empty")
        _require(
            metadata_before.st_size <= FOUNDATION_LEDGER_MAXIMUM_OCTETS,
            "foundation ledger exceeds the reviewed predecode octet bound",
        )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(FOUNDATION_LEDGER_MAXIMUM_OCTETS + 1)
        metadata_after = os.fstat(descriptor)
        _require(
            (
                metadata_after.st_dev,
                metadata_after.st_ino,
                metadata_after.st_mode,
                metadata_after.st_size,
                metadata_after.st_mtime_ns,
                metadata_after.st_ctime_ns,
            )
            == (
                metadata_before.st_dev,
                metadata_before.st_ino,
                metadata_before.st_mode,
                metadata_before.st_size,
                metadata_before.st_mtime_ns,
                metadata_before.st_ctime_ns,
            ),
            "foundation ledger changed while it was read",
        )
    finally:
        os.close(descriptor)
    _require(
        len(raw) <= FOUNDATION_LEDGER_MAXIMUM_OCTETS,
        "foundation ledger exceeds the reviewed predecode octet bound",
    )
    _require(
        len(raw) == metadata_before.st_size,
        "foundation ledger size changed or was short-read",
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise FoundationValidationError(
            f"cannot decode foundation ledger: {exc}"
        ) from exc
    _validate_json_nesting(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except (json.JSONDecodeError, FoundationValidationError, RecursionError) as exc:
        raise FoundationValidationError(
            f"invalid foundation ledger JSON: {exc}"
        ) from exc
    _require(type(value) is dict, "foundation ledger root is not an exact object")
    _require_json_scalar_strings(value)
    try:
        canonical = _canonical_pretty_bytes(value)
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise FoundationValidationError(
            f"cannot canonicalize foundation ledger JSON: {exc}"
        ) from exc
    _require(
        raw == canonical,
        "foundation ledger bytes are not canonical pretty JSON",
    )
    return raw, value


def _validate_foundation(path: Path) -> dict[str, Any]:
    raw, ledger = _load_ledger(path)
    root_order = (
        "canonicalization_version",
        "component_status",
        "foundation_ledger_version",
        "identifier_profile_specs",
        "measurement_schema_version",
        "metadata_shape_declarations",
        "surface_assignments",
        "unicode_source_specs",
    )
    _exact_object(ledger, root_order, label="foundation ledger")
    _require(
        ledger["canonicalization_version"] == CANONICALIZATION_VERSION,
        "foundation canonicalization version differs",
    )
    _require(
        ledger["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "foundation measurement schema version differs",
    )
    _require(
        ledger["foundation_ledger_version"] == FOUNDATION_LEDGER_VERSION,
        "foundation ledger version differs",
    )
    _require(
        ledger["component_status"] == FOUNDATION_COMPONENT_STATUS,
        "foundation component status differs",
    )
    _require(
        ledger["metadata_shape_declarations"] == _expected_metadata_shapes(),
        "foundation metadata-shape declarations differ",
    )

    source_specs = ledger["unicode_source_specs"]
    _require(
        type(source_specs) is list and len(source_specs) == 6,
        "foundation must contain exactly six Unicode source specs",
    )
    for position, source in enumerate(source_specs, 1):
        _exact_object(
            source,
            SOURCE_PAYLOAD_ORDER,
            label=f"Unicode source spec {position}",
        )
        _require(
            type(source["byte_count"]) is int
            and 0 < source["byte_count"] <= SAFE_UINT_MAX,
            f"Unicode source spec {position} byte count is invalid",
        )
        _require(
            type(source["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None,
            f"Unicode source spec {position} SHA-256 is invalid",
        )
    _require(
        source_specs == _expected_source_specs(),
        "Unicode source specifications differ from the frozen six-record authority",
    )

    source_records: list[dict[str, Any]] = []
    source_id_by_name: dict[str, str] = {}
    for source in source_specs:
        payload = {member: source[member] for member in SOURCE_PAYLOAD_ORDER}
        semantic_id = _semantic_id(SOURCE_DOMAIN, payload)
        source_id_by_name[source["source_name"]] = semantic_id
        source_records.append({**payload, "unicode_source_record_id": semantic_id})

    profile_specs = ledger["identifier_profile_specs"]
    _require(
        type(profile_specs) is list and len(profile_specs) == 3,
        "foundation must contain exactly three identifier profile specs",
    )
    for position, profile in enumerate(profile_specs, 1):
        _exact_object(
            profile,
            PROFILE_SPEC_ORDER,
            label=f"identifier profile spec {position}",
        )
        parsed_trim = tuple(
            _code_point(item) for item in profile["edge_trim_code_points"]
        )
        _require(
            len(parsed_trim) == 29
            and len(set(parsed_trim)) == 29
            and tuple(sorted(parsed_trim)) == parsed_trim,
            f"identifier profile spec {position} edge-trim set is not exact",
        )
    _require(
        profile_specs == _expected_profile_specs(),
        "identifier profile specifications differ from the frozen A/B/C authority",
    )

    profile_records: list[dict[str, Any]] = []
    profile_semantic_id_by_profile_id: dict[str, str] = {}
    for profile in profile_specs:
        payload = {
            "profile_id": profile["profile_id"],
            "unicode_version": profile["unicode_version"],
            "normalization_form": profile["normalization_form"],
            "maximum_scalar_values": profile["maximum_scalar_values"],
            "maximum_utf8_octets": profile["maximum_utf8_octets"],
            "forbidden_code_point_ranges": profile["forbidden_code_point_ranges"],
            "edge_trim_code_points": profile["edge_trim_code_points"],
            "unicode_source_record_ids": [
                source_id_by_name[name] for name in profile["unicode_source_names"]
            ],
        }
        _require(
            tuple(payload) == PROFILE_PAYLOAD_ORDER,
            f"identifier profile {profile['profile_id']} payload order differs",
        )
        semantic_id = _semantic_id(PROFILE_DOMAIN, payload)
        profile_semantic_id_by_profile_id[profile["profile_id"]] = semantic_id
        profile_records.append(
            {**payload, "unicode_identifier_profile_id": semantic_id}
        )

    surface_assignments = ledger["surface_assignments"]
    _require(
        type(surface_assignments) is list and len(surface_assignments) == 10,
        "foundation must contain exactly ten Unicode surface assignments",
    )
    for position, assignment in enumerate(surface_assignments, 1):
        _exact_object(
            assignment,
            SURFACE_ASSIGNMENT_ORDER,
            label=f"surface assignment {position}",
        )
        _require(
            type(assignment["surface_position"]) is int
            and assignment["surface_position"] == position,
            "surface assignment positions are not contiguous from one",
        )
        _require(
            type(assignment["nullable"]) is bool,
            f"surface assignment {position} nullability is invalid",
        )
    _require(
        surface_assignments == _expected_surface_assignments(),
        "Unicode surface assignments differ from the frozen ten-surface authority",
    )
    surface_counts = Counter(
        assignment["profile_id"] for assignment in surface_assignments
    )
    _require(
        {profile_id: surface_counts[profile_id] for profile_id in PROFILE_LIMITS}
        == {profile_id: limits[2] for profile_id, limits in PROFILE_LIMITS.items()},
        "Unicode surface assignment profile counts differ",
    )

    _require(
        _sha256_bytes(raw) == FOUNDATION_LEDGER_SHA256,
        "foundation ledger bytes differ from the independently frozen hash",
    )
    ordered_source_records = sorted(
        source_records,
        key=lambda item: item["unicode_source_record_id"],
    )
    ordered_profile_records = sorted(
        profile_records,
        key=lambda item: item["unicode_identifier_profile_id"],
    )
    report = {
        "component_status": FOUNDATION_COMPONENT_STATUS,
        "foundation_ledger_sha256": _sha256_bytes(raw),
        "foundation_ledger_version": FOUNDATION_LEDGER_VERSION,
        "identifier_profile_count": len(ordered_profile_records),
        "ordered_unicode_identifier_profile_ids": [
            item["unicode_identifier_profile_id"] for item in ordered_profile_records
        ],
        "ordered_unicode_source_record_ids": [
            item["unicode_source_record_id"] for item in ordered_source_records
        ],
        "profile_semantic_id_by_profile_id": dict(
            sorted(profile_semantic_id_by_profile_id.items())
        ),
        "surface_assignment_count": len(surface_assignments),
        "surface_assignment_count_by_profile_id": {
            profile_id: surface_counts[profile_id] for profile_id in PROFILE_LIMITS
        },
        "surface_assignments_sha256": _sha256_bytes(
            _canonical_bytes(surface_assignments)
        ),
        "unicode_source_count": len(ordered_source_records),
        "unicode_source_record_id_by_source_name": dict(
            sorted(source_id_by_name.items())
        ),
    }
    report["foundation_component_sha256"] = _sha256_bytes(_canonical_bytes(report))
    return report


def _parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    namespace = _parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        report = _validate_foundation(namespace.ledger)
        print(_canonical_bytes(report).decode("utf-8"))
        return 0
    except (FoundationValidationError, OSError) as exc:
        print(
            f"Raw-V8 Step-2 external-schema V2 foundation error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
