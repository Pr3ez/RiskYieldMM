"""Independent fail-first target for S1-A4/A4-P6 six-case qualification.

This module freezes the externally observable six-case producer/verifier and
parent-runner contract.  It imports no implementation or predecessor module.
The current accepted fail-first state has five pipeline failures (the five
pilot cases not yet supported by the bounded case-5 pair) and one missing
parent-runner failure.  Contract, hostile-oracle, and case-5 control tests must
remain green while those six implementation failures are retired deliberately.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
MANIFEST = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
PRODUCER = (
    ROOT / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
RUNNER = ROOT / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"

BOUNDARY_OCTETS = 27_334
BOUNDARY_SHA256 = "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
BOUNDARY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
SEED_OCTETS = 13_419_905
SEED_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
MANIFEST_OCTETS = 15_560
MANIFEST_SHA256 = "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
MANIFEST_ID = "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
SOURCE_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
REGISTRY_ID = "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
RULE_LITERAL_SHA256 = "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
RECURRENCE_CATALOG_ID = (
    "743ab1fdf8f15da1b38331dc23fcf79dd4a89c2767013afba421107deeeecbcd"
)
F2_CATALOG_ID = "17a2258cde720b2868e9bb538fbd3d702c299a0db7d8fb5215938578d217d0fe"

CONTEXT_OBJECT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV2V4_9F_RawV8"
)
RECORD_REFERENCE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8"
)
ROW_CONTEXT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRowContextClosureV2V4_9F_RawV8"
)

EXPECTED_CASES = (
    {
        "pilot_position": 1,
        "case_position": 5,
        "case_kind": "MAXIMUM_PUBLICATION_ROW",
        "plan_id": "d8149e3965dbdb9ed708860af0599463eafcfe2d428404ec7dea9aa20873cbe0",
        "coverage_tag": "SMALL_BOOLEAN_EXHAUSTIVE_CANONICAL_LENGTH",
        "type_name": "CapacityMeasurementBoolValueV1",
        "alternative_name": None,
        "row_kind": "INTRINSIC_RECORD",
        "profile_id": None,
        "upper_bound_mode": "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
        "root_kind": "LOGICAL_PLAN_TEMPLATE",
        "application_count": 0,
        "context_reference_count": 0,
    },
    {
        "pilot_position": 2,
        "case_position": 24,
        "case_kind": "MAXIMUM_PUBLICATION_ROW",
        "plan_id": "428ff735837b841e66103d64cbcd4af7ceaf88d009c38229ad5e4cde0ab30d67",
        "coverage_tag": "OWNER_MEMBER_TAGGED_UNION_AND_OWNER_CODEC",
        "type_name": "CapacityMeasurementOperationResultBody",
        "alternative_name": "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
        "row_kind": "INTRINSIC_UNION_ALTERNATIVE",
        "profile_id": None,
        "upper_bound_mode": "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
        "root_kind": "LOGICAL_PLAN_TEMPLATE",
        "application_count": 0,
        "context_reference_count": 0,
    },
    {
        "pilot_position": 3,
        "case_position": 54,
        "case_kind": "MAXIMUM_PUBLICATION_ROW",
        "plan_id": "4eeedde2c223693e62a2b89a2016b43f9954496771189616ad68ac8cf21e6da1",
        "coverage_tag": "RAW_STRING_ARRAY_CARDINALITY_ORDERING_AND_ESCAPING",
        "type_name": "CapacityMeasurementVocabularyDefinitionV1",
        "alternative_name": None,
        "row_kind": "INTRINSIC_RECORD",
        "profile_id": None,
        "upper_bound_mode": "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
        "root_kind": "LOGICAL_PLAN_TEMPLATE",
        "application_count": 0,
        "context_reference_count": 0,
    },
    {
        "pilot_position": 4,
        "case_position": 69,
        "case_kind": "MAXIMUM_PUBLICATION_ROW",
        "plan_id": "b991ffb7f0ea927d854228bcc52524e39fee7e88080d9171753b03cc59589fcb",
        "coverage_tag": "LOCAL_SHUTDOWN_OUTER_RESULT_EXACT_APPLICATION_AND_CODEC",
        "type_name": "CapacityMeasurementOperationResultEvidence",
        "alternative_name": None,
        "row_kind": "OUTER_RESULT_BOUNDARY_FIXTURE",
        "profile_id": "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4",
        "upper_bound_mode": "EXACT_LEGAL_DOMAIN",
        "root_kind": "PROFILE_CONDITIONING_PROGRAM",
        "application_count": 1,
        "context_reference_count": 2,
    },
    {
        "pilot_position": 5,
        "case_position": 435,
        "case_kind": "MAXIMUM_PUBLICATION_ROW",
        "plan_id": "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a",
        "coverage_tag": "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_AND_SAFE_SUPERSET",
        "type_name": "TargetObservationV2",
        "alternative_name": None,
        "row_kind": "CHECKPOINT_ROOT_COORDINATE",
        "profile_id": "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540",
        "upper_bound_mode": "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
        "root_kind": "PROFILE_CONDITIONING_PROGRAM",
        "application_count": 137,
        "context_reference_count": 71,
    },
    {
        "pilot_position": 6,
        "case_position": 475,
        "case_kind": "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY",
        "plan_id": "2d46a1b71c9466fd3268b93dbc3e4a62a4855dd0324f4cfecfbb60d4589bbbc0",
        "coverage_tag": "LOCAL_SHUTDOWN_EXACT_MINIMALITY_AND_SINGLE_MASK_REJECTION",
        "type_name": None,
        "alternative_name": None,
        "row_kind": None,
        "profile_id": "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4",
        "upper_bound_mode": "EXACT_LEGAL_DOMAIN",
        "root_kind": "LOCAL_SHUTDOWN_ANALYTIC_CATALOG",
        "application_count": 1,
        "context_reference_count": 2,
    },
)
PILOT_CASES = tuple(row["case_position"] for row in EXPECTED_CASES)

EXPECTED_F2 = (
    ("SCOPE_CASE_COUNT", "SUM", 1, 475),
    ("LOGICAL_DESCRIPTOR_OCCURRENCE_COUNT", "SUM", 2_102_272, 29_190_144),
    ("RECURRENCE_STATE_ENTRY_COUNT", "SUM", 1_024, 66_560),
    ("RECURRENCE_TRANSITION_ATTEMPT_COUNT", "SUM", 1_024, 417_792),
    (
        "LOGICAL_UNBATCHED_TRANSITION_EQUIVALENT_COUNT",
        "SUM",
        4_204_544,
        170_915_840,
    ),
    ("RECURRENCE_BATCH_APPLICATION_COUNT", "SUM", 1_024, 2_048),
    ("CACHE_ENTRY_COUNT", "SUM", 1_024, 66_560),
    ("CACHE_KEY_CANONICAL_OCTETS", "SUM", 106_496, 45_088_768),
    ("DERIVATION_CANONICALIZATION_INPUT_OCTETS", "SUM", 790_528, 329_252_864),
    ("DERIVATION_CANONICALIZATION_OUTPUT_OCTETS", "SUM", 880_640, 368_050_176),
    ("DERIVATION_HASH_PREIMAGE_OCTETS", "SUM", 1_482_752, 619_708_416),
    ("INTRINSIC_RULE_EVALUATION_COUNT", "SUM", 1_024, 5_120),
    ("CROSS_RULE_EVALUATION_COUNT", "SUM", 49_152, 4_199_424),
    ("APPLICATION_EVALUATION_COUNT", "SUM", 1_024, 47_104),
    ("MAXIMUM_DERIVATION_DEPTH", "MAXIMUM", 17, 17),
    ("MAXIMUM_ITERATION_DEPTH", "MAXIMUM", 569, 569),
    ("PEAK_RETAINED_DERIVATION_OCTETS", "MAXIMUM", 57_344, 57_344),
    ("DERIVATION_RESULT_CANONICAL_OCTETS", "SUM", 40_960, 15_728_640),
)

RUNNER_MARKER = "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1"
PRODUCER_MARKER = "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1"
VERIFIER_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"
PRODUCER_ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_"
VERIFIER_ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"
RUNNER_ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PILOT_RUNNER_"


class QualificationReject(ValueError):
    """Independent target-oracle rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationReject(message)


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value, f"duplicate key: {key}")
        value[key] = item
    return value


def _reject_number(value: str) -> Any:
    raise QualificationReject(f"floating or non-finite number: {value}")


def _strict_load(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(not text.startswith("\ufeff"), "BOM")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise QualificationReject("strict JSON") from error
    _require(type(value) is dict, "JSON root is not an object")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")


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
    ).encode("utf-8", errors="strict")


def _pretty_bytes_in_order(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8", errors="strict")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _seed_semantic_id(seed: dict[str, Any], domain: str, payload: Any) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": seed["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": seed["measurement_schema_version"],
            }
        )
    )


def _closed(value: Any, names: list[str], label: str) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} is not an object")
    _require(set(value) == set(names), f"{label} members differ")
    return value


def _sha(value: Any, label: str) -> str:
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} is not lowercase SHA-256",
    )
    return value


def _authorities() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    boundary_raw = BOUNDARY.read_bytes()
    seed_raw = SEED.read_bytes()
    manifest_raw = MANIFEST.read_bytes()
    _require(len(boundary_raw) == BOUNDARY_OCTETS, "boundary octets")
    _require(_sha256(boundary_raw) == BOUNDARY_SHA256, "boundary hash")
    _require(len(seed_raw) == SEED_OCTETS, "seed octets")
    _require(_sha256(seed_raw) == SEED_SHA256, "seed hash")
    _require(len(manifest_raw) == MANIFEST_OCTETS, "manifest octets")
    _require(_sha256(manifest_raw) == MANIFEST_SHA256, "manifest hash")
    boundary = _strict_load(boundary_raw)
    seed = _strict_load(seed_raw)
    manifest = _strict_load(manifest_raw)
    _require(
        boundary_raw == _pretty_bytes_in_order(boundary),
        "boundary physical encoding",
    )
    _require(seed_raw == _pretty_bytes_in_order(seed), "seed physical encoding")
    _require(
        manifest_raw == _pretty_bytes_in_order(manifest),
        "manifest physical encoding",
    )
    boundary_payload = {
        name: item
        for name, item in boundary.items()
        if name != "constructive_boundary_id"
    }
    _require(
        boundary["constructive_boundary_id"]
        == _semantic_id(BOUNDARY_DOMAIN, boundary_payload)
        == BOUNDARY_ID,
        "boundary semantic identity",
    )
    _require(seed["seed_catalog_id"] == SEED_ID, "seed semantic identity")
    _require(
        manifest["finalization_manifest_id"] == MANIFEST_ID,
        "manifest semantic identity",
    )
    return boundary, seed, manifest


def _case_maps(
    seed: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    cases = {
        row["case_position"]: row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
    }
    plans = {
        row["case_position"]: row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
    }
    return cases, plans


def _contains_forbidden_member(value: Any, forbidden: set[str]) -> bool:
    if type(value) is dict:
        return any(
            key in forbidden or _contains_forbidden_member(item, forbidden)
            for key, item in value.items()
        )
    if type(value) is list:
        return any(_contains_forbidden_member(item, forbidden) for item in value)
    return False


def _isolated_environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_producer(
    case_position: int, output_root: Path
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(PRODUCER),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(BOUNDARY),
            "--case-position",
            str(case_position),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
        timeout=600,
    )


def _run_verifier(
    candidate_root: Path, output_root: Path
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(VERIFIER),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(BOUNDARY),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
        timeout=600,
    )


def _assert_silent_success(
    completed: subprocess.CompletedProcess[bytes], label: str
) -> None:
    assert completed.returncode == 0, (
        f"{label}: exit={completed.returncode}; "
        f"stderr={completed.stderr.decode('utf-8', errors='replace')!r}"
    )
    assert completed.stdout == completed.stderr == b"", label


def _closure_snapshot(root: Path) -> tuple[tuple[str, str, int, int, str], ...]:
    rows: list[tuple[str, str, int, int, str]] = []
    for path in sorted([root, *root.rglob("*")]):
        metadata = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if stat.S_ISDIR(metadata.st_mode):
            kind = "DIRECTORY"
            digest = ""
        elif stat.S_ISREG(metadata.st_mode):
            kind = "REGULAR_FILE"
            digest = _sha256(path.read_bytes())
        else:
            kind = "FORBIDDEN"
            digest = ""
        rows.append(
            (
                relative,
                kind,
                stat.S_IMODE(metadata.st_mode),
                metadata.st_size,
                digest,
            )
        )
    return tuple(rows)


def _context_reference_ids(value: Any) -> list[str]:
    result: list[str] = []
    if type(value) is dict:
        if value.get("reference_kind") == "CONTEXT_OBJECT":
            result.append(value.get("maximum_context_object_id"))
        for item in value.values():
            result.extend(_context_reference_ids(item))
    elif type(value) is list:
        for item in value:
            result.extend(_context_reference_ids(item))
    return result


def _validate_record_references(value: Any, seed: dict[str, Any]) -> None:
    if type(value) is dict:
        kind = value.get("reference_kind")
        if kind is not None:
            names_by_kind = {
                "WITNESS_RECORD": [
                    "reference_kind",
                    "record_type_name",
                    "record_identity_field",
                    "record_identity",
                    "record_canonical_byte_length",
                    "record_canonical_sha256",
                    "maximum_record_reference_id",
                ],
                "CONTEXT_OBJECT": [
                    "reference_kind",
                    "maximum_context_object_id",
                    "record_type_name",
                    "record_identity_field",
                    "record_identity",
                    "record_canonical_byte_length",
                    "record_canonical_sha256",
                    "maximum_record_reference_id",
                ],
                "V4_INVENTORY_POINTER": [
                    "reference_kind",
                    "source_inventory_sha256",
                    "inventory_json_pointer",
                    "record_type_name",
                    "record_identity_field",
                    "record_identity",
                    "record_canonical_byte_length",
                    "record_canonical_sha256",
                    "maximum_record_reference_id",
                ],
            }
            _require(kind in names_by_kind, "unknown maximum-record reference kind")
            reference = _closed(value, names_by_kind[kind], "maximum-record reference")
            payload = {name: reference[name] for name in names_by_kind[kind][:-1]}
            _require(
                reference["maximum_record_reference_id"]
                == _seed_semantic_id(seed, RECORD_REFERENCE_DOMAIN, payload),
                "maximum-record reference identity",
            )
            _sha(reference["record_canonical_sha256"], "record-reference hash")
            if kind == "CONTEXT_OBJECT":
                _sha(reference["maximum_context_object_id"], "context-object ID")
            if kind == "V4_INVENTORY_POINTER":
                _require(
                    reference["source_inventory_sha256"] == SOURCE_INVENTORY_ID,
                    "V4 inventory semantic identity",
                )
        else:
            for item in value.values():
                _validate_record_references(item, seed)
    elif type(value) is list:
        for item in value:
            _validate_record_references(item, seed)


def _validate_context_objects(
    root: Path,
    entries: Any,
    seed: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[str, ...]:
    _require(type(entries) is list, "context entries are not an array")
    boundary, _seed, _manifest = _authorities()
    schema = boundary["candidate_bundle_contract"]["context_object_entry_schema"]
    descriptor_by_type = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    ids: list[str] = []
    expected_files: set[str] = {"candidate.json"}
    for position, entry in enumerate(entries, 1):
        _closed(entry, schema["ordered_member_names"], "context-object entry")
        _require(entry["context_object_position"] == position, "context position")
        object_id = _sha(
            entry["claimed_maximum_context_object_id"], "claimed context-object ID"
        )
        _require(object_id not in ids, "duplicate context-object ID")
        ids.append(object_id)
        expected_path = f"context_objects/{object_id[:2]}/{object_id}.json"
        _require(
            entry["repository_relative_path"] == expected_path,
            "context-object path",
        )
        path = root / expected_path
        _require(path.is_file() and not path.is_symlink(), "context-object file")
        raw = path.read_bytes()
        record = _strict_load(raw)
        _require(raw == _canonical_bytes(record), "context-object encoding")
        _require(entry["raw_octet_count"] == len(raw), "context-object octets")
        _require(entry["raw_sha256"] == _sha256(raw), "context-object hash")
        type_name = entry["record_type_name"]
        _require(type_name in descriptor_by_type, "context-object type")
        descriptor = descriptor_by_type[type_name]
        identity_field = descriptor["identity_field"]
        _require(type(identity_field) is str, "context object lacks identity field")
        _require(identity_field in record, "context object lacks record identity")
        payload = {
            "maximum_protocol_sha256": MANIFEST_SHA256,
            "source_inventory_sha256": SOURCE_INVENTORY_ID,
            "external_schema_registry_id": REGISTRY_ID,
            "rule_literal_authority_sha256": RULE_LITERAL_SHA256,
            "record_type_name": type_name,
            "record_identity_field": identity_field,
            "record_identity": record[identity_field],
            "record_canonical_byte_length": len(raw),
            "record_canonical_sha256": _sha256(raw),
            "record": record,
        }
        _require(
            object_id == _seed_semantic_id(seed, CONTEXT_OBJECT_DOMAIN, payload),
            "context-object semantic identity",
        )
        expected_files.add(expected_path)
    _require(ids == sorted(ids), "context-object ID order")
    actual_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    _require(actual_files == expected_files, "candidate file closure")
    return tuple(ids)


def _validate_candidate(
    root: Path,
    case_position: int,
    boundary: dict[str, Any],
    seed: dict[str, Any],
    manifest: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[dict[str, Any], bytes, tuple[str, ...]]:
    _require(root.is_dir() and not root.is_symlink(), "candidate root")
    _require(
        {path.name for path in root.iterdir()} == {"candidate.json", "context_objects"},
        "candidate root members",
    )
    _require((root / "context_objects").is_dir(), "candidate context root")
    raw = (root / "candidate.json").read_bytes()
    candidate = _strict_load(raw)
    _require(raw == _pretty_bytes(candidate), "candidate physical encoding")
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    _closed(candidate, schema["ordered_member_names"], "candidate envelope")
    cases, plans = _case_maps(seed)
    case = cases[case_position]
    plan = plans[case_position]
    expected = {
        "candidate_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": case_position,
        "case_kind": case["case_kind"],
        "case_binding": case["case_binding"],
        "logical_count_plan_id": plan["logical_count_plan_id"],
    }
    for name, value in expected.items():
        _require(candidate[name] == value, f"candidate {name}")
    payload = candidate["candidate_payload"]
    alternatives = boundary["candidate_bundle_contract"][
        "candidate_payload_tagged_union"
    ]["ordered_alternative_records"]
    alternative = next(
        (
            row
            for row in alternatives
            if row["candidate_kind"] == payload.get("candidate_kind")
        ),
        None,
    )
    _require(alternative is not None, "candidate payload tag")
    _closed(payload, alternative["ordered_member_names"], "candidate payload")
    _require(
        alternative["required_case_kind"] == case["case_kind"], "payload/case kind"
    )
    forbidden = set(
        boundary["candidate_bundle_contract"]["forbidden_producer_claim_member_names"]
    )
    _require(
        not _contains_forbidden_member(candidate, forbidden), "producer proof claim"
    )
    if case["case_kind"] == "MAXIMUM_PUBLICATION_ROW":
        _require(type(payload["witness_record"]) is dict, "maximum witness")
        _require(
            payload["scope_witness_context"] is None
            or type(payload["scope_witness_context"]) is dict,
            "maximum scope context",
        )
        entries = payload["ordered_context_object_entries"]
        _validate_record_references(payload["scope_witness_context"], seed)
    else:
        _require(type(payload["mutated_spec"]) is dict, "local mutated spec")
        _require(
            type(payload["prospective_result"]) is dict, "local prospective result"
        )
        entries = []
    context_ids = _validate_context_objects(root, entries, seed, registry)
    _require(
        sorted(set(_context_reference_ids(payload))) == list(context_ids),
        "candidate context-reference closure",
    )
    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    _require(
        candidate["constructive_candidate_id"]
        == _semantic_id(schema["identity_domain"], identity_payload),
        "candidate identity",
    )
    return candidate, raw, context_ids


def _validate_resource_report(
    report: Any,
    boundary: dict[str, Any],
    manifest: dict[str, Any],
    *,
    plan_id: str,
    derivation_certificate_id: str,
) -> tuple[int, ...]:
    schema = boundary["verifier_output_contract"]["proof_resource_report_schema"]
    report = _closed(report, schema["ordered_member_names"], "resource report")
    _require(
        report["resource_report_version"] == schema["version_literal"],
        "resource report version",
    )
    _require(report["maximum_protocol_sha256"] == MANIFEST_SHA256, "resource protocol")
    _require(report["derivation_plan_id"] == plan_id, "resource plan")
    _require(
        report["derivation_certificate_id"] == derivation_certificate_id,
        "resource certificate",
    )
    _require(report["resource_limit_catalog_id"] == F2_CATALOG_ID, "F2 catalog")
    measurements = report["ordered_resource_measurements"]
    limits = manifest["ordered_f2_limit_records"]
    _require(
        type(measurements) is list and len(measurements) == len(limits) == 18,
        "resource vector length",
    )
    values: list[int] = []
    for measurement, limit in zip(measurements, limits, strict=True):
        _closed(
            measurement,
            ["metric_position", "metric_name", "measured_value"],
            "resource measurement",
        )
        _require(
            measurement["metric_position"] == limit["metric_position"],
            "resource position",
        )
        _require(measurement["metric_name"] == limit["metric_name"], "resource name")
        measured = measurement["measured_value"]
        _require(
            type(measured) is int and 0 <= measured <= limit["f2_per_case"],
            "per-case F2",
        )
        values.append(measured)
    payload = {name: report[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        report["proof_resource_report_id"]
        == _semantic_id(schema["identity_domain"], payload),
        "resource report identity",
    )
    return tuple(values)


def _validate_verified_result(
    root: Path,
    candidate: dict[str, Any],
    candidate_raw: bytes,
    context_ids: tuple[str, ...],
    boundary: dict[str, Any],
    seed: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[bytes, bytes, tuple[int, ...]]:
    output = boundary["verifier_output_contract"]
    paths = output["verified_bundle_paths"]
    maximum = candidate["case_kind"] == "MAXIMUM_PUBLICATION_ROW"
    result_name = paths["maximum_result"] if maximum else paths["local_result"]
    expected_root_names = {paths["receipt"], result_name, paths["context_root"]}
    _require(
        root.is_dir() and {path.name for path in root.iterdir()} == expected_root_names,
        "verified root closure",
    )
    result_raw = (root / result_name).read_bytes()
    receipt_raw = (root / paths["receipt"]).read_bytes()
    result = _strict_load(result_raw)
    receipt = _strict_load(receipt_raw)
    _require(result_raw == _pretty_bytes(result), "result physical encoding")
    _require(receipt_raw == _pretty_bytes(receipt), "receipt physical encoding")
    payload = candidate["candidate_payload"]
    plans = _case_maps(seed)[1]
    plan = plans[candidate["case_position"]]
    if maximum:
        schema = output["maximum_attainer_schema"]
        id_name = "maximum_attainer_id"
        _closed(result, schema["ordered_member_names"], "maximum result")
        _require(
            result["artifact_version"] == schema["version_literal"], "maximum version"
        )
        _require(result["witness_kind"] == schema["witness_kind"], "witness kind")
        binding = candidate["case_binding"]
        _require(result["type_name"] == binding["type_name"], "maximum type")
        _require(
            result["alternative_name"] == binding["alternative_name"],
            "maximum alternative",
        )
        _require(
            result["constraint_scope_profile_id"]
            == binding["constraint_scope_profile_id"],
            "maximum profile",
        )
        _require(
            result["witness_record"] == payload["witness_record"], "maximum witness"
        )
        _require(
            result["scope_witness_context"] == payload["scope_witness_context"],
            "maximum scope context",
        )
        witness_raw = _canonical_bytes(result["witness_record"])
        _require(result["canonical_byte_length"] == len(witness_raw), "witness length")
        _require(result["canonical_sha256"] == _sha256(witness_raw), "witness hash")
        _require(
            result["certified_analytic_maximum_octets"] == len(witness_raw),
            "P3 attainment",
        )
        _require(
            result["required_context_object_count"] == len(context_ids), "context count"
        )
        _require(
            result["ordered_required_context_object_ids"] == list(context_ids),
            "context IDs",
        )
        certificate_schema = output["upper_bound_certificate_schema"]
        certificate = _closed(
            result["upper_bound_certificate"],
            certificate_schema["ordered_member_names"],
            "upper-bound certificate",
        )
        _require(
            not set(certificate_schema["forbidden_member_names"]).intersection(
                certificate
            ),
            "forbidden certificate member",
        )
        _require(
            certificate["certificate_version"] == certificate_schema["version_literal"],
            "certificate version",
        )
        _require(
            certificate["maximum_protocol_sha256"] == MANIFEST_SHA256,
            "certificate protocol",
        )
        _require(
            certificate["derivation_plan_id"] == plan["logical_count_plan_id"],
            "certificate plan",
        )
        _require(
            certificate["derivation_catalog_id"] == RECURRENCE_CATALOG_ID,
            "certificate recurrence",
        )
        _require(
            certificate["upper_bound_mode"] == plan["upper_bound_mode"],
            "certificate mode",
        )
        _require(
            certificate["ordered_safe_relaxation_rule_ids"]
            == plan["ordered_safe_relaxation_rule_ids"],
            "certificate relaxations",
        )
        _require(
            certificate["certified_upper_bound_octets"] == len(witness_raw),
            "P2/P3 equality",
        )
        certificate_payload = {
            name: certificate[name]
            for name in certificate_schema["ordered_member_names"][:-1]
        }
        _require(
            certificate["upper_bound_certificate_id"]
            == _semantic_id(certificate_schema["identity_domain"], certificate_payload),
            "certificate identity",
        )
        derivation_certificate_id = certificate["upper_bound_certificate_id"]
        _require(
            result["constraint_scope_id"] == certificate["derivation_scope_id"],
            "scope/certificate binding",
        )
        row_context_payload = {
            "maximum_protocol_sha256": MANIFEST_SHA256,
            "source_inventory_sha256": SOURCE_INVENTORY_ID,
            "constraint_scope_id": result["constraint_scope_id"],
            "required_context_object_count": len(context_ids),
            "ordered_required_context_object_ids": list(context_ids),
        }
        _require(
            result["row_context_closure_id"]
            == _semantic_id(ROW_CONTEXT_DOMAIN, row_context_payload),
            "row context identity",
        )
    else:
        schema = output["local_shutdown_result_schema"]
        id_name = "local_shutdown_unrepresentable_id"
        _closed(result, schema["ordered_member_names"], "local result")
        _require(
            result["artifact_version"] == schema["version_literal"], "local version"
        )
        _require(
            result["constraint_scope_profile_id"]
            == candidate["case_binding"]["constraint_scope_profile_id"],
            "local profile",
        )
        _require(
            result["mutated_spec"] == payload["mutated_spec"], "local mutated spec"
        )
        _require(
            result["prospective_result"] == payload["prospective_result"],
            "local prospective result",
        )
        _require(
            result["prospective_result_canonical_byte_length"]
            == len(_canonical_bytes(payload["prospective_result"])),
            "local prospective length",
        )
        _require(
            type(result["minimality_certificate"]) is dict,
            "local minimality certificate",
        )
        _require(
            type(result["changed_limit_field_count"]) is int
            and result["changed_limit_field_count"] > 0,
            "local changed count",
        )
        _require(
            type(result["sum_absolute_integer_deltas"]) is int
            and result["sum_absolute_integer_deltas"] > 0,
            "local objective",
        )
        derivation_certificate_id = _sha(
            result["minimality_certificate"].get("minimality_certificate_id"),
            "minimality certificate ID",
        )
    for name, expected in (
        ("canonicalization_version", boundary["canonicalization_version"]),
        ("measurement_schema_version", boundary["measurement_schema_version"]),
        ("maximum_protocol_sha256", MANIFEST_SHA256),
        ("source_inventory_sha256", SOURCE_INVENTORY_ID),
        ("external_schema_registry_id", REGISTRY_ID),
        ("rule_literal_authority_sha256", RULE_LITERAL_SHA256),
    ):
        _require(result[name] == expected, f"result {name}")
    measurements = _validate_resource_report(
        result["proof_resource_report"],
        boundary,
        manifest,
        plan_id=plan["logical_count_plan_id"],
        derivation_certificate_id=derivation_certificate_id,
    )
    result_payload = {
        name: result[name] for name in schema["ordered_member_names"][:-1]
    }
    _require(
        result[id_name] == _semantic_id(schema["identity_domain"], result_payload),
        "result identity",
    )

    receipt_schema = output["verification_receipt_schema"]
    _closed(receipt, receipt_schema["ordered_member_names"], "verification receipt")
    cases, plans = _case_maps(seed)
    case_position = candidate["case_position"]
    expected_receipt = {
        "receipt_version": receipt_schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": case_position,
        "case_kind": cases[case_position]["case_kind"],
        "case_binding": cases[case_position]["case_binding"],
        "logical_count_plan_id": plans[case_position]["logical_count_plan_id"],
        "constructive_candidate_id": candidate["constructive_candidate_id"],
        "candidate_raw_octets": len(candidate_raw),
        "candidate_raw_sha256": _sha256(candidate_raw),
        "verification_status": (
            receipt_schema["maximum_status"]
            if maximum
            else receipt_schema["local_status"]
        ),
        "result_artifact_kind": "MAXIMUM_ATTAINER"
        if maximum
        else "LOCAL_SHUTDOWN_RESULT",
        "result_artifact_id": result[id_name],
        "result_repository_relative_path": result_name,
        "result_raw_octets": len(result_raw),
        "result_raw_sha256": _sha256(result_raw),
    }
    for name, expected in expected_receipt.items():
        _require(receipt[name] == expected, f"receipt {name}")
    _require(
        [
            row["claimed_maximum_context_object_id"]
            for row in receipt["ordered_verified_context_object_entries"]
        ]
        == list(context_ids),
        "receipt context closure",
    )
    receipt_payload = {
        name: receipt[name] for name in receipt_schema["ordered_member_names"][:-1]
    }
    _require(
        receipt["verification_receipt_id"]
        == _semantic_id(receipt_schema["identity_domain"], receipt_payload),
        "receipt identity",
    )
    candidate_context = root.parent / "candidate" / "context_objects"
    verified_context = root / paths["context_root"]
    _require(
        _closure_snapshot(verified_context) == _closure_snapshot(candidate_context),
        "verified context bytes differ from candidate closure",
    )
    return result_raw, receipt_raw, measurements


def _pipeline_once(
    base: Path, case_position: int
) -> tuple[tuple[tuple[str, str, int, int, str], ...], bytes, bytes, tuple[int, ...]]:
    base.mkdir(mode=0o700)
    boundary, seed, manifest = _authorities()
    registry_path = (
        ROOT
        / boundary["authority_contract"]["seed_authority"]["repository_relative_path"]
    )
    _require(registry_path == SEED, "seed authority path")
    registry = _strict_load(
        (
            ROOT
            / "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
        ).read_bytes()
    )
    candidate_root = base / "candidate"
    producer = _run_producer(case_position, candidate_root)
    _assert_silent_success(
        producer,
        f"A4_P6_CASE_{case_position}_PRODUCER_NOT_QUALIFIED",
    )
    candidate, candidate_raw, context_ids = _validate_candidate(
        candidate_root,
        case_position,
        boundary,
        seed,
        manifest,
        registry,
    )
    before = _closure_snapshot(candidate_root)
    verified_root = base / "verified"
    verifier = _run_verifier(candidate_root, verified_root)
    _assert_silent_success(
        verifier,
        f"A4_P6_CASE_{case_position}_VERIFIER_NOT_QUALIFIED",
    )
    _require(
        _closure_snapshot(candidate_root) == before, "candidate mutated by verifier"
    )
    result_raw, receipt_raw, measurements = _validate_verified_result(
        verified_root,
        candidate,
        candidate_raw,
        context_ids,
        boundary,
        seed,
        manifest,
    )
    return before, result_raw, receipt_raw, measurements


def _runner_source_surface(raw: bytes) -> None:
    boundary, _seed, _manifest = _authorities()
    try:
        source = raw.decode("utf-8", errors="strict")
        tree = ast.parse(source)
    except (UnicodeError, SyntaxError) as error:
        raise QualificationReject("runner source syntax") from error
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) is str
    }
    _require(RUNNER_MARKER in strings, "runner source marker")
    _require(
        PRODUCER_MARKER not in source and VERIFIER_MARKER not in source,
        "runner copied child marker",
    )
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            _require(
                node.level == 0 and node.module is not None, "runner relative import"
            )
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    independence = boundary["independence_contract"]
    _require(
        imports <= set(independence["allowed_standard_library_import_roots"]),
        "runner import allowlist",
    )
    _require(
        imports.isdisjoint(set(independence["forbidden_import_roots"])),
        "runner forbidden import",
    )
    _require(
        calls.isdisjoint({"__import__", "compile", "eval", "exec", "system", "popen"}),
        "runner dynamic or shell execution",
    )
    _require(
        {"fork", "execve", "wait4", "setrlimit"} <= calls, "runner process controls"
    )
    for required in (
        PRODUCER.relative_to(ROOT).as_posix(),
        VERIFIER.relative_to(ROOT).as_posix(),
        "--case-position",
        "--candidate-root",
        "--write-output-root",
        "--check-output-root",
    ):
        _require(
            required in strings or required in source, f"runner surface {required}"
        )


def _run_runner(mode: str, output_root: Path) -> subprocess.CompletedProcess[bytes]:
    _require(mode in {"write", "check"}, "runner mode")
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(RUNNER),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(BOUNDARY),
            f"--{mode}-output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
        timeout=3_600,
    )


def _file_closure_digest(root: Path) -> tuple[int, str]:
    records = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_file():
            raw = path.read_bytes()
            total += len(raw)
            records.append(
                {
                    "repository_relative_path": path.relative_to(root).as_posix(),
                    "raw_octets": len(raw),
                    "raw_sha256": _sha256(raw),
                }
            )
    return total, _sha256(_canonical_bytes(records))


def _validate_pilot_output(root: Path) -> bytes:
    boundary, seed, manifest = _authorities()
    _require(root.is_dir() and not root.is_symlink(), "pilot root")
    _require(
        {path.name for path in root.iterdir()}
        == {"constructive_pilot_manifest.json", "cases"},
        "pilot root members",
    )
    raw = (root / "constructive_pilot_manifest.json").read_bytes()
    value = _strict_load(raw)
    _require(raw == _pretty_bytes(value), "pilot manifest encoding")
    pilot = boundary["pilot_contract"]
    schema = pilot["pilot_manifest_schema"]
    _closed(value, schema["ordered_member_names"], "pilot manifest")
    for name, expected in (
        ("pilot_version", pilot["pilot_version"]),
        ("canonicalization_version", boundary["canonicalization_version"]),
        ("protocol_version", boundary["protocol_version"]),
        ("seed_catalog_id", seed["seed_catalog_id"]),
        ("finalization_manifest_id", manifest["finalization_manifest_id"]),
        ("pilot_status", pilot["pilot_status"]),
    ):
        _require(value[name] == expected, f"pilot {name}")
    roles = {
        row["role_name"]: row
        for row in boundary["implementation_role_contract"]["ordered_role_records"]
    }
    for member, role in (
        ("producer_authority", "SEPARATE_PRODUCER"),
        ("verifier_authority", "INDEPENDENT_VERIFIER"),
        ("runner_authority", "PARENT_PILOT_RUNNER"),
    ):
        authority = _closed(
            value[member],
            schema["implementation_authority_ordered_member_names"],
            member,
        )
        role_record = roles[role]
        source = ROOT / role_record["repository_relative_path"]
        source_raw = source.read_bytes()
        _require(
            authority
            == {
                "repository_relative_path": role_record["repository_relative_path"],
                "raw_octets": len(source_raw),
                "raw_sha256": _sha256(source_raw),
                "source_marker": role_record["source_marker"],
            },
            f"{member} binding",
        )
    rows = value["ordered_case_result_entries"]
    expected_rows = pilot["ordered_pilot_case_records"]
    _require(type(rows) is list and len(rows) == 6, "pilot row count")
    aggregate = [0] * 18
    for expected, row in zip(expected_rows, rows, strict=True):
        _closed(row, schema["case_result_entry_ordered_member_names"], "pilot case row")
        for name in (
            "pilot_position",
            "case_position",
            "case_kind",
            "logical_count_plan_id",
        ):
            _require(row[name] == expected[name], f"pilot row {name}")
        case_root = (
            root
            / "cases"
            / f"{expected['pilot_position']:04d}-{expected['case_position']:04d}"
        )
        candidate_root = case_root / "candidate"
        verified_root = case_root / "verified"
        _require(
            {path.name for path in case_root.iterdir()} == {"candidate", "verified"},
            "pilot case closure",
        )
        candidate_raw = (candidate_root / "candidate.json").read_bytes()
        candidate = _strict_load(candidate_raw)
        receipt_raw = (verified_root / "verification_receipt.json").read_bytes()
        receipt = _strict_load(receipt_raw)
        result_name = (
            "maximum_attainer.json"
            if expected["case_kind"] == "MAXIMUM_PUBLICATION_ROW"
            else "local_shutdown_unrepresentable.json"
        )
        result_raw = (verified_root / result_name).read_bytes()
        result = _strict_load(result_raw)
        candidate_octets, candidate_digest = _file_closure_digest(candidate_root)
        verified_octets, verified_digest = _file_closure_digest(verified_root)
        result_id = result.get("maximum_attainer_id") or result.get(
            "local_shutdown_unrepresentable_id"
        )
        _require(
            row["constructive_candidate_id"] == candidate["constructive_candidate_id"],
            "pilot candidate ID",
        )
        _require(
            row["candidate_root_raw_octets"] == candidate_octets,
            "pilot candidate octets",
        )
        _require(
            row["candidate_root_sha256"] == candidate_digest, "pilot candidate digest"
        )
        _require(
            row["verification_receipt_id"] == receipt["verification_receipt_id"],
            "pilot receipt ID",
        )
        _require(row["verified_result_artifact_id"] == result_id, "pilot result ID")
        _require(
            row["verified_result_root_raw_octets"] == verified_octets,
            "pilot verified octets",
        )
        _require(
            row["verified_result_root_sha256"] == verified_digest,
            "pilot verified digest",
        )
        report = result["proof_resource_report"]
        for index, measurement in enumerate(report["ordered_resource_measurements"]):
            mode = EXPECTED_F2[index][1]
            if mode == "SUM":
                aggregate[index] += measurement["measured_value"]
            else:
                aggregate[index] = max(aggregate[index], measurement["measured_value"])
    for measured, expected in zip(aggregate, EXPECTED_F2, strict=True):
        _require(measured <= expected[3], f"pilot full-run F2 {expected[0]}")
    manifest_payload = {
        name: value[name] for name in schema["ordered_member_names"][:-1]
    }
    _require(
        value["constructive_pilot_manifest_id"]
        == _semantic_id(schema["identity_domain"], manifest_payload),
        "pilot manifest identity",
    )
    return raw


def test_six_case_authority_is_exact_complete_and_not_producer_selected() -> None:
    boundary, seed, _manifest = _authorities()
    pilot = boundary["pilot_contract"]
    rows = pilot["ordered_pilot_case_records"]
    cases, plans = _case_maps(seed)
    assert len(rows) == len(EXPECTED_CASES) == 6
    for expected, row in zip(EXPECTED_CASES, rows, strict=True):
        assert row == {
            "pilot_position": expected["pilot_position"],
            "case_position": expected["case_position"],
            "case_kind": expected["case_kind"],
            "logical_count_plan_id": expected["plan_id"],
            "coverage_tag": expected["coverage_tag"],
        }
        case = cases[expected["case_position"]]
        plan = plans[expected["case_position"]]
        assert case["case_kind"] == expected["case_kind"]
        assert plan["logical_count_plan_id"] == expected["plan_id"]
        assert plan["upper_bound_mode"] == expected["upper_bound_mode"]
        assert plan["logical_root_reference"]["root_kind"] == expected["root_kind"]
        assert (
            plan["scope_summary"]["application_invocation_count"]
            == expected["application_count"]
        )
        assert (
            plan["scope_summary"]["context_record_reference_count"]
            == expected["context_reference_count"]
        )
        binding = case["case_binding"]
        assert binding.get("type_name") == expected["type_name"]
        assert binding.get("alternative_name") == expected["alternative_name"]
        assert binding.get("row_kind") == expected["row_kind"]
        assert binding["constraint_scope_profile_id"] == expected["profile_id"]
    assert pilot["case_selection_rule"].startswith("EXACT_SEED_CASE_AND_PLAN_BINDINGS")
    assert (
        pilot["acceptance_rule"]
        == "ALL_SIX_CASES_ACCEPT_OR_THE_COMPLETE_PILOT_IS_NO_GO"
    )
    assert pilot["publication_rule"].endswith(
        "DO_NOT_SELECT_OR_AUTHORIZE_THE_474_ROW_PUBLICATION"
    )


def test_six_case_stressors_cover_scalar_owner_array_profile_root_and_local() -> None:
    _boundary, seed, _manifest = _authorities()
    plans = _case_maps(seed)[1]
    assert plans[5]["scope_summary"]["internal_scope_case_count"] == 1
    assert plans[24]["root_step_position"] == 39
    assert plans[54]["root_step_position"] == 5
    assert plans[69]["scope_summary"]["cross_rule_evaluation_count"] == 1
    assert plans[69]["scope_summary"]["direct_cross_expression_node_count"] == 3
    assert plans[435]["scope_summary"]["constructed_context_occurrence_count"] == 67
    assert plans[435]["scope_summary"]["observation_count"] == 67
    assert plans[435]["scope_summary"]["cross_rule_evaluation_count"] == 12_531
    assert plans[435]["scope_summary"]["direct_cross_expression_node_count"] == 125_431
    assert plans[475]["local_analytic_catalog_id"] is not None
    assert plans[475]["root_step_position"] is None


def test_f2_limits_are_exact_immutable_and_complete() -> None:
    boundary, _seed, manifest = _authorities()
    rows = manifest["ordered_f2_limit_records"]
    assert [row["metric_position"] for row in rows] == list(range(1, 19))
    assert (
        tuple(
            (
                row["metric_name"],
                row["full_run_aggregation"],
                row["f2_per_case"],
                row["f2_full_run"],
            )
            for row in rows
        )
        == EXPECTED_F2
    )
    assert all(row["required_per_case"] <= row["f2_per_case"] for row in rows)
    assert all(row["required_full_run"] <= row["f2_full_run"] for row in rows)
    resources = boundary["resource_enforcement_contract"]
    assert (
        resources["semantic_metric_limit_source"]
        == "FINALIZATION_MANIFEST_ORDERED_F2_LIMIT_RECORDS"
    )
    assert resources["pilot_excess_policy"].startswith("CONTROLLED_NO_GO")
    assert (
        "NO_PILOT_OBSERVATION_MAY_RAISE_OR_REPAIR"
        in boundary["pilot_contract"]["limit_rule"]
    )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":1.5}',
        b'{"a":NaN}',
        b'\xef\xbb\xbf{"a":1}',
        b"\xff",
    ],
)
def test_target_strict_parser_rejects_noncanonical_json(raw: bytes) -> None:
    with pytest.raises(QualificationReject):
        _strict_load(raw)


def _case5_fixture() -> dict[str, Any]:
    boundary, seed, manifest = _authorities()
    cases, plans = _case_maps(seed)
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    value = {
        "candidate_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": 5,
        "case_kind": cases[5]["case_kind"],
        "case_binding": copy.deepcopy(cases[5]["case_binding"]),
        "logical_count_plan_id": plans[5]["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": {"kind": "BOOL", "value": False},
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        },
    }
    value["constructive_candidate_id"] = _semantic_id(schema["identity_domain"], value)
    return value


def _publish_case5_fixture(root: Path, value: dict[str, Any]) -> None:
    root.mkdir(mode=0o700)
    (root / "context_objects").mkdir(mode=0o700)
    (root / "candidate.json").write_bytes(_pretty_bytes(value))


def _mutate_candidate_id(value: dict[str, Any]) -> None:
    value["constructive_candidate_id"] = "0" * 64


def _mutate_candidate_plan(value: dict[str, Any]) -> None:
    value["logical_count_plan_id"] = "0" * 64
    boundary, _seed, _manifest = _authorities()
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    value["constructive_candidate_id"] = _semantic_id(
        schema["identity_domain"],
        {name: value[name] for name in schema["ordered_member_names"][:-1]},
    )


def _mutate_candidate_claim(value: dict[str, Any]) -> None:
    value["candidate_payload"]["upper_bound_certificate"] = {}
    boundary, _seed, _manifest = _authorities()
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    value["constructive_candidate_id"] = _semantic_id(
        schema["identity_domain"],
        {name: value[name] for name in schema["ordered_member_names"][:-1]},
    )


@pytest.mark.parametrize(
    "mutation",
    [_mutate_candidate_id, _mutate_candidate_plan, _mutate_candidate_claim],
    ids=["identity", "plan", "producer-proof-claim"],
)
def test_candidate_oracle_rejects_hostile_resealed_fixtures(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    value = _case5_fixture()
    mutation(value)
    root = tmp_path / "candidate"
    _publish_case5_fixture(root, value)
    boundary, seed, manifest = _authorities()
    registry = _strict_load(
        (
            ROOT
            / "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
        ).read_bytes()
    )
    with pytest.raises(QualificationReject):
        _validate_candidate(root, 5, boundary, seed, manifest, registry)


def test_qualification_target_does_not_import_implementations_or_predecessor() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert roots.isdisjoint({"riskyieldmm", "scripts", "tests", "importlib"})
    assert "spec_from_file_location" not in calls
    forbidden_fragments = (
        "maximum_protocol_" + "pilot.v1",
        "ordered_expected_" + "case_results",
        "expected_" + "witness_record",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)


def test_case5_pipeline_control_remains_exact_deterministic_and_immutable(
    tmp_path: Path,
) -> None:
    first = _pipeline_once(tmp_path / "first", 5)
    second = _pipeline_once(tmp_path / "second", 5)
    assert first == second


@pytest.mark.parametrize("case_position", PILOT_CASES[1:])
def test_remaining_pilot_pipeline_is_exact_deterministic_and_candidate_immutable(
    tmp_path: Path, case_position: int
) -> None:
    first = _pipeline_once(tmp_path / "first", case_position)
    second = _pipeline_once(tmp_path / "second", case_position)
    assert first == second, f"A4_P6_CASE_{case_position}_NONDETERMINISTIC"


def test_parent_runner_exists_and_obeys_frozen_isolation_surface() -> None:
    assert RUNNER.is_file() and not RUNNER.is_symlink(), (
        "A4_P6_PARENT_RUNNER_MISSING: implement the frozen parent-owned runner "
        "only after this six-case target is accepted"
    )
    _runner_source_surface(RUNNER.read_bytes())


def test_parent_runner_emits_exact_two_run_all_or_nothing_pilot(tmp_path: Path) -> None:
    if not RUNNER.is_file():
        pytest.skip("A4-P6 expected blocker: parent runner is not implemented")
    first = tmp_path / "first"
    second = tmp_path / "second"
    _assert_silent_success(_run_runner("write", first), "A4_P6_PARENT_RUNNER_WRITE_1")
    first_manifest = _validate_pilot_output(first)
    first_snapshot = _closure_snapshot(first)
    _assert_silent_success(_run_runner("check", first), "A4_P6_PARENT_RUNNER_CHECK")
    assert _closure_snapshot(first) == first_snapshot
    _assert_silent_success(_run_runner("write", second), "A4_P6_PARENT_RUNNER_WRITE_2")
    second_manifest = _validate_pilot_output(second)
    assert first_manifest == second_manifest
    assert _closure_snapshot(first) == _closure_snapshot(second)


def test_parent_runner_has_bounded_silent_invalid_cli_when_implemented() -> None:
    if not RUNNER.is_file():
        pytest.skip("A4-P6 expected blocker: parent runner is not implemented")
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(RUNNER), "--invalid"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
        timeout=30,
    )
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr.startswith(RUNNER_ERROR_PREFIX)
    assert completed.stderr.count(b"\n") == 1
