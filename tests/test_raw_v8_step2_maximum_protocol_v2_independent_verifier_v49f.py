"""Acceptance and adversarial tests for the bounded S1-A4/A4-V verifier."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
BOUNDARY_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SEED_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)

CONSTRAINT_SCOPE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeV2V4_9F_RawV8"
)
ROW_CONTEXT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRowContextClosureV2V4_9F_RawV8"
)
EVALUATION_SEMANTICS = (
    "FULL_GRAPH_EXACT_IJSON_INTRINSIC_DEPENDENCY_POSTORDER_THEN_"
    "LEXICAL_APPLICATION_NAME_THEN_INVOCATION_ORDINAL_V1"
)
MANIFEST_SHA256 = "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
SOURCE_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
REGISTRY_ID = "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
LITERAL_SHA256 = "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
CASE5_STREAM_SHA256 = "79375d5ecab2af215e9259524c7f16b41a2b5737cda7f5897a3cd6c272c0b314"
CASE5_RESOURCE_VECTOR = [
    1,
    3,
    4,
    8,
    8,
    0,
    4,
    2684,
    8104,
    10384,
    33573,
    0,
    0,
    0,
    3,
    3,
    3783,
    1359,
]


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


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _authorities() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        json.loads(BOUNDARY_PATH.read_bytes()),
        json.loads(SEED_PATH.read_bytes()),
        json.loads(MANIFEST_PATH.read_bytes()),
    )


def _candidate(
    case_position: int = 5, witness: dict[str, Any] | None = None
) -> dict[str, Any]:
    boundary, seed, manifest = _authorities()
    case = seed["case_universe_catalog"]["ordered_case_bindings"][case_position - 1]
    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        case_position - 1
    ]
    value = {
        "candidate_version": boundary["candidate_bundle_contract"][
            "candidate_envelope_schema"
        ]["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": case_position,
        "case_kind": case["case_kind"],
        "case_binding": copy.deepcopy(case["case_binding"]),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": (
                {"kind": "BOOL", "value": False} if witness is None else witness
            ),
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        },
    }
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    value["constructive_candidate_id"] = _semantic_id(schema["identity_domain"], value)
    return value


def _publish_candidate(root: Path, candidate: dict[str, Any]) -> bytes:
    root.mkdir(mode=0o700)
    (root / "context_objects").mkdir(mode=0o700)
    raw = _pretty_bytes(candidate)
    (root / "candidate.json").write_bytes(raw)
    return raw


def _run(candidate_root: Path, output_root: Path) -> subprocess.CompletedProcess[bytes]:
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
            str(BOUNDARY_PATH),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
    )


def _load_verified(
    output_root: Path,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    result_raw = (output_root / "maximum_attainer.json").read_bytes()
    receipt_raw = (output_root / "verification_receipt.json").read_bytes()
    result = json.loads(result_raw)
    receipt = json.loads(receipt_raw)
    assert result_raw == _pretty_bytes(result)
    assert receipt_raw == _pretty_bytes(receipt)
    return result, result_raw, receipt, receipt_raw


def _assert_identity(value: dict[str, Any], id_name: str, domain: str) -> None:
    payload = {name: child for name, child in value.items() if name != id_name}
    assert value[id_name] == _semantic_id(domain, payload)


def _assert_rejected(
    completed: subprocess.CompletedProcess[bytes], output: Path
) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_")
    assert completed.stderr.count(b"\n") == 1
    assert not output.exists()


def test_case5_result_recomputes_exact_bound_identities_and_resources(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    candidate_root = tmp_path / "candidate"
    candidate_raw = _publish_candidate(candidate_root, candidate)
    output_root = tmp_path / "verified"
    completed = _run(candidate_root, output_root)
    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == completed.stderr == b""
    result, result_raw, receipt, _receipt_raw = _load_verified(output_root)

    scope_payload = {
        "constraint_scope": "INTRINSIC_TYPE",
        "measured_type_name": "CapacityMeasurementBoolValueV1",
        "alternative_name": None,
        "measurement_binding": {
            "binding_kind": "SELF_RECORD",
            "validation_root_type_name": "CapacityMeasurementBoolValueV1",
            "measured_value_typed_member_path": [],
            "sequence_binding_name": None,
            "sequence_ordinal": None,
        },
        "constraint_scope_profile_id": None,
        "external_schema_registry_id": REGISTRY_ID,
        "rule_literal_authority_sha256": LITERAL_SHA256,
        "maximum_protocol_sha256": MANIFEST_SHA256,
        "source_inventory_sha256": None,
        "evaluation_semantics": EVALUATION_SEMANTICS,
    }
    scope_id = _semantic_id(CONSTRAINT_SCOPE_DOMAIN, scope_payload)
    row_context_id = _semantic_id(
        ROW_CONTEXT_DOMAIN,
        {
            "maximum_protocol_sha256": MANIFEST_SHA256,
            "source_inventory_sha256": SOURCE_INVENTORY_ID,
            "constraint_scope_id": scope_id,
            "required_context_object_count": 0,
            "ordered_required_context_object_ids": [],
        },
    )
    assert result["constraint_scope_id"] == scope_id
    assert result["row_context_closure_id"] == row_context_id
    assert result["witness_record"] == {"kind": "BOOL", "value": False}
    assert result["canonical_byte_length"] == 29
    assert result["certified_analytic_maximum_octets"] == 29
    assert result["codec_byte_bound_relation"] == "LE"
    assert result["codec_octet_limit"] == 3072
    assert result["codec_slack_octets"] == 3043

    certificate = result["upper_bound_certificate"]
    report = result["proof_resource_report"]
    assert certificate["streamed_derivation_result_sha256"] == CASE5_STREAM_SHA256
    assert [
        row["measured_value"] for row in report["ordered_resource_measurements"]
    ] == CASE5_RESOURCE_VECTOR
    boundary, _seed, _manifest = _authorities()
    output = boundary["verifier_output_contract"]
    _assert_identity(
        certificate,
        "upper_bound_certificate_id",
        output["upper_bound_certificate_schema"]["identity_domain"],
    )
    _assert_identity(
        report,
        "proof_resource_report_id",
        output["proof_resource_report_schema"]["identity_domain"],
    )
    _assert_identity(
        result,
        "maximum_attainer_id",
        output["maximum_attainer_schema"]["identity_domain"],
    )
    _assert_identity(
        receipt,
        "verification_receipt_id",
        output["verification_receipt_schema"]["identity_domain"],
    )
    assert receipt["candidate_raw_octets"] == len(candidate_raw)
    assert receipt["candidate_raw_sha256"] == _sha256(candidate_raw)
    assert receipt["result_raw_octets"] == len(result_raw)
    assert receipt["result_raw_sha256"] == _sha256(result_raw)
    assert stat.S_IMODE(output_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((output_root / "maximum_attainer.json").stat().st_mode) == 0o600
    assert (
        stat.S_IMODE((output_root / "verification_receipt.json").stat().st_mode)
        == 0o600
    )


def test_case5_verification_is_byte_deterministic(tmp_path: Path) -> None:
    outputs = []
    for ordinal in (1, 2):
        candidate_root = tmp_path / f"candidate-{ordinal}"
        _publish_candidate(candidate_root, _candidate())
        output_root = tmp_path / f"verified-{ordinal}"
        completed = _run(candidate_root, output_root)
        assert completed.returncode == 0, completed.stderr.decode()
        outputs.append(
            (
                (output_root / "maximum_attainer.json").read_bytes(),
                (output_root / "verification_receipt.json").read_bytes(),
            )
        )
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    "witness",
    [
        {"kind": "BOOL", "value": True},
        {"kind": "BOOL", "value": 0},
        {"kind": "OTHER", "value": False},
        {"kind": "BOOL", "value": False, "extra": None},
    ],
    ids=["legal-but-not-maximal", "integer-is-not-boolean", "bad-tag", "extra-member"],
)
def test_case5_rejects_nonattaining_or_illegal_witnesses_without_output(
    tmp_path: Path, witness: dict[str, Any]
) -> None:
    candidate_root = tmp_path / "candidate"
    _publish_candidate(candidate_root, _candidate(witness=witness))
    output_root = tmp_path / "verified"
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_verifier_rejects_unimplemented_case_without_output(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    _publish_candidate(candidate_root, _candidate(case_position=24, witness={}))
    output_root = tmp_path / "verified"
    completed = _run(candidate_root, output_root)
    _assert_rejected(completed, output_root)
    assert b"UNSUPPORTED_CASE" in completed.stderr


def _hardlink_candidate(candidate_root: Path, tmp_path: Path) -> None:
    os.link(candidate_root / "candidate.json", tmp_path / "external-hardlink.json")


def _symlink_candidate(candidate_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "external-candidate.json"
    target.write_bytes((candidate_root / "candidate.json").read_bytes())
    (candidate_root / "candidate.json").unlink()
    (candidate_root / "candidate.json").symlink_to(target)


def _unexpected_context(candidate_root: Path, _tmp_path: Path) -> None:
    (candidate_root / "context_objects" / "unexpected.json").write_text("{}")


@pytest.mark.parametrize(
    "mutation",
    [_hardlink_candidate, _symlink_candidate, _unexpected_context],
    ids=["hardlink", "symlink", "unexpected-context"],
)
def test_verifier_rejects_hostile_candidate_filesystem_without_output(
    tmp_path: Path, mutation: Callable[[Path, Path], None]
) -> None:
    candidate_root = tmp_path / "candidate"
    _publish_candidate(candidate_root, _candidate())
    mutation(candidate_root, tmp_path)
    output_root = tmp_path / "verified"
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_verifier_does_not_overwrite_existing_output(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    _publish_candidate(candidate_root, _candidate())
    output_root = tmp_path / "verified"
    output_root.mkdir()
    sentinel = output_root / "sentinel"
    sentinel.write_bytes(b"retain")
    completed = _run(candidate_root, output_root)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.count(b"\n") == 1
    assert sentinel.read_bytes() == b"retain"


def test_verifier_leaves_candidate_bytes_unchanged_and_no_private_leftover(
    tmp_path: Path,
) -> None:
    candidate_root = tmp_path / "candidate"
    candidate_raw = _publish_candidate(candidate_root, _candidate())
    output_root = tmp_path / "verified"
    completed = _run(candidate_root, output_root)
    assert completed.returncode == 0, completed.stderr.decode()
    assert (candidate_root / "candidate.json").read_bytes() == candidate_raw
    assert not [path for path in tmp_path.iterdir() if ".private." in path.name]
