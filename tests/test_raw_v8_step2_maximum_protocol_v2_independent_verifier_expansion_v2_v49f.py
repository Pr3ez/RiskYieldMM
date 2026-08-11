"""Independent A4-P6-V2 acceptance for exact profile case 69.

The positive fixture is constructed directly from frozen V4 inventory bytes and
the published local analytic formula.  This module imports neither the producer,
the verifier, the preflight implementations, nor the accepted typed runtime.
The candidate remains data: the verifier must independently resolve the signed
spec, execute P1, derive P2, measure P3, and meter the event stream.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
BOUNDARY = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
SUCCESSOR_BOUNDARY = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
INVENTORY = ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json"
VERIFIER_RELATIVE = VERIFIER.relative_to(ROOT)
BOUNDARY_RELATIVE = BOUNDARY.relative_to(ROOT)
SUCCESSOR_BOUNDARY_RELATIVE = SUCCESSOR_BOUNDARY.relative_to(ROOT)
SEED_RELATIVE = SEED.relative_to(ROOT)
MANIFEST_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
SEED_DELTA_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
MANIFEST_DELTA_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
TARGET_DELTA_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json"
)
PREDECESSOR_TARGET_RELATIVE = Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py"
)
TYPED_RUNTIME_RELATIVE = Path(
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)

CASE_POSITION = 69
EXACT_MAXIMUM = 2_581
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
PLAN_ID = "b991ffb7f0ea927d854228bcc52524e39fee7e88080d9171753b03cc59589fcb"
PROFILE_ID = "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
PROGRAM_ID = "6912414e364c4117822c7ad0d24d1436d46f29e945ed076140785f5c0c9fc442"
ANALYTIC_ID = "759b3fbd70f3a36c0a6309ec35c4f5cd8efda7cf01d23bcd5e52e290ff29f0e0"
SPEC_ID = "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
APPLICATION_ID = "770d99b0001802ceb6bdc044b9b55ce3cfd319754e9b9716c10d0b3d2e214f18"
APPLICATION_NAME = "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
CROSS_RULE_ID = "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1"
SPEC_POINTER = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"

SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_MANIFEST_ID = "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
SUCCESSOR_PROTOCOL_SHA256 = "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
SUCCESSOR_F2_ID = "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
SOURCE_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
RECORD_REFERENCE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8"
)

EXPECTED_RESOURCE_VECTOR = (
    1,
    2_101_890,
    157,
    829,
    4_204_335,
    7,
    157,
    105_752,
    673_168,
    763_519,
    1_380_238,
    6,
    1,
    1,
    14,
    32,
    50_016,
    36_961,
)
EXPECTED_STREAM_SHA256 = "7965e977eca8aa43ce84c97391a1ae4c51dfd2f79fa20e80ea7b6110ea5c808f"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


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


def _seed_semantic_id(domain: str, payload: Any) -> str:
    seed = _load(SEED)
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


def _reseal_result(result: dict[str, Any]) -> None:
    payload = {
        name: result[name]
        for name in (
            "candidate_id",
            "attempt_id",
            "operation_kind",
            "result_type",
            "result",
        )
    }
    result["result_evidence_id"] = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": result["canonicalization_version"],
                "domain": result["record_domain"],
                "payload": payload,
                "schema_version": result["measurement_schema_version"],
            }
        )
    )


def _case69_witness() -> dict[str, Any]:
    inventory = _load(INVENTORY)
    witness = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )

    # The frozen baseline is 2,504 bytes.  Replacing JSON null with one
    # lowercase SHA-256 adds 62 bytes; replacing the one-digit trace count by
    # the largest safe integer adds 15.  The signed-spec limits and the result
    # intrinsic array/count relations remain unchanged.
    witness["result"]["local_shutdown_deadline_evidence_event_id"] = "0" * 64
    witness["result"]["shutdown_trace_step_count"] = SAFE_INTEGER_MAXIMUM
    _reseal_result(witness)
    assert len(_canonical_bytes(witness)) == EXACT_MAXIMUM
    return witness


def _record_reference(reference_payload: dict[str, Any]) -> dict[str, Any]:
    reference = dict(reference_payload)
    reference["maximum_record_reference_id"] = _seed_semantic_id(
        RECORD_REFERENCE_DOMAIN, reference_payload
    )
    return reference


def _scope_context(witness: dict[str, Any]) -> dict[str, Any]:
    inventory = _load(INVENTORY)
    spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    witness_raw = _canonical_bytes(witness)
    spec_raw = _canonical_bytes(spec)
    return {
        "context_kind": "OUTER_RESULT_APPLICATION",
        "constraint_scope_profile_id": PROFILE_ID,
        "operation_result_record_reference": _record_reference(
            {
                "reference_kind": "WITNESS_RECORD",
                "record_type_name": "CapacityMeasurementOperationResultEvidence",
                "record_identity_field": "result_evidence_id",
                "record_identity": witness["result_evidence_id"],
                "record_canonical_byte_length": len(witness_raw),
                "record_canonical_sha256": _sha256(witness_raw),
            }
        ),
        "operation_spec_authority_reference": _record_reference(
            {
                "reference_kind": "V3_INVENTORY_POINTER",
                "source_inventory_sha256": SOURCE_INVENTORY_ID,
                "inventory_json_pointer": SPEC_POINTER,
                "record_type_name": "CapacityMeasurementOperationSpec",
                "record_identity_field": "operation_spec_id",
                "record_identity": spec["operation_spec_id"],
                "record_canonical_byte_length": len(spec_raw),
                "record_canonical_sha256": _sha256(spec_raw),
            }
        ),
        "ordered_application_invocations": [
            {
                "application_name": APPLICATION_NAME,
                "application_invocation_ordinal": 0,
                "bound_observation_ordinal": None,
            }
        ],
    }


def _case_and_plan() -> tuple[dict[str, Any], dict[str, Any]]:
    seed = _load(SEED)
    case = seed["case_universe_catalog"]["ordered_case_bindings"][CASE_POSITION - 1]
    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        CASE_POSITION - 1
    ]
    assert case["case_position"] == plan["case_position"] == CASE_POSITION
    assert plan["logical_count_plan_id"] == PLAN_ID
    assert plan["profile_conditioning_program_id"] == PROGRAM_ID
    return case, plan


def _reseal_candidate(candidate: dict[str, Any]) -> None:
    schema = _load(BOUNDARY)["candidate_bundle_contract"]["candidate_envelope_schema"]
    payload = {name: candidate[name] for name in schema["ordered_member_names"][:-1]}
    candidate["constructive_candidate_id"] = _semantic_id(
        schema["identity_domain"], payload
    )


def _candidate(
    *,
    mutate_witness: Callable[[dict[str, Any]], None] | None = None,
    mutate_scope: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    boundary = _load(BOUNDARY)
    case, plan = _case_and_plan()
    witness = _case69_witness()
    if mutate_witness is not None:
        mutate_witness(witness)
        _reseal_result(witness)
    scope = _scope_context(witness)
    if mutate_scope is not None:
        mutate_scope(scope)
    candidate = {
        "candidate_version": boundary["candidate_bundle_contract"][
            "candidate_envelope_schema"
        ]["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": SUCCESSOR_SEED_ID,
        "finalization_manifest_id": SUCCESSOR_MANIFEST_ID,
        "case_position": CASE_POSITION,
        "case_kind": case["case_kind"],
        "case_binding": copy.deepcopy(case["case_binding"]),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": witness,
            "scope_witness_context": scope,
            "ordered_context_object_entries": [],
        },
    }
    _reseal_candidate(candidate)
    return candidate


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
            str(SUCCESSOR_BOUNDARY),
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


def _assert_rejected(
    completed: subprocess.CompletedProcess[bytes], output_root: Path
) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"
    )
    assert b"INTERNAL_FAIL_CLOSED" not in completed.stderr
    assert completed.stderr.count(b"\n") == 1
    assert not output_root.exists()


def _assert_identity(value: dict[str, Any], member: str, domain: str) -> None:
    payload = {name: child for name, child in value.items() if name != member}
    assert value[member] == _semantic_id(domain, payload)


def _copy_minimal_authority_repository(destination: Path) -> None:
    boundary = _load(BOUNDARY)
    seed = _load(SEED)
    seed_delta = _load(ROOT / SEED_DELTA_RELATIVE)
    relatives = {
        VERIFIER_RELATIVE,
        BOUNDARY_RELATIVE,
        SUCCESSOR_BOUNDARY_RELATIVE,
        SEED_RELATIVE,
        MANIFEST_RELATIVE,
        SEED_DELTA_RELATIVE,
        MANIFEST_DELTA_RELATIVE,
        TARGET_DELTA_RELATIVE,
        PREDECESSOR_TARGET_RELATIVE,
        TYPED_RUNTIME_RELATIVE,
    }
    relatives.update(
        Path(row["repository_relative_path"])
        for row in seed["ordered_authority_binding_records"]
    )
    legacy = boundary["legacy_v1_exclusion_contract"]
    relatives.update(
        Path(legacy[name]["repository_relative_path"])
        for name in (
            "rejected_protocol_authority",
            "rejected_bootstrap_authority",
            "accepted_rejection_authority",
        )
    )
    relatives.update(
        Path(row["repository_relative_path"])
        for row in seed_delta["exactness_theorem_authority"][
            "ordered_source_authority_records"
        ]
    )
    for relative in sorted(relatives):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def _output_snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_v2_attainer_formula_is_independent_exact_and_signed_spec_bounded() -> None:
    inventory = _load(INVENTORY)
    seed = _load(SEED)
    spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    result = _case69_witness()
    local = seed["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    formula = local["batch_unsaturated_program"]
    batch_limit = spec["spec"]["maximum_terminal_ingress_batches"]
    derived = (
        formula["constant_octets"]
        + formula["linear_coefficient"] * batch_limit
        + formula["decimal_width_coefficient"] * len(str(batch_limit))
    )
    assert spec["operation_spec_id"] == SPEC_ID
    assert local["local_shutdown_analytic_catalog_id"] == ANALYTIC_ID
    assert formula["opcode"] == "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1"
    assert derived == local["baseline_attainable_maximum_octets"] == EXACT_MAXIMUM
    assert len(_canonical_bytes(result)) == derived

    body = result["result"]
    signed = spec["spec"]
    assert body["terminal_outcome"] == signed["expected_terminal_outcome"]
    for result_member, spec_member in (
        ("final_terminal_ingress_batch_count", "maximum_terminal_ingress_batches"),
        ("final_terminal_ingress_ciphertext_octets", "maximum_terminal_ingress_ciphertext_octets"),
        ("final_terminal_ingress_plaintext_octets", "maximum_terminal_ingress_plaintext_octets"),
        ("final_terminal_socket_receive_call_count", "maximum_terminal_socket_receive_calls"),
        ("final_terminal_tls_record_count", "maximum_terminal_tls_records"),
        ("final_terminal_tls_unwrap_iteration_count", "maximum_terminal_tls_unwrap_iterations"),
        ("final_terminal_zero_progress_iteration_count", "maximum_terminal_zero_progress_iterations"),
        ("final_terminal_ingress_parser_unit_count", "maximum_terminal_ingress_parser_units"),
        ("final_terminal_ingress_automatic_output_count", "maximum_terminal_ingress_automatic_outputs"),
        ("final_websocket_send_attempt_count", "maximum_websocket_send_attempts"),
        ("final_tls_control_send_attempt_count", "maximum_tls_control_send_attempts"),
        ("final_peer_shutdown_poll_count", "maximum_peer_shutdown_polls"),
    ):
        assert body[result_member] <= signed[spec_member]


def test_v2_rejects_case69_analytic_endpoint_authority_tamper(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "minimal-repository"
    repository.mkdir()
    _copy_minimal_authority_repository(repository)
    seed_path = repository / SEED_RELATIVE
    raw = seed_path.read_bytes()
    frozen = b'"baseline_attainable_maximum_octets": 2581'
    assert raw.count(frozen) == 1
    seed_path.write_bytes(raw.replace(frozen, b'"baseline_attainable_maximum_octets": 2582'))

    candidate_root = repository / "candidate"
    output_root = repository / "output"
    _publish_candidate(candidate_root, _candidate())
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(repository / VERIFIER_RELATIVE),
            "--repository-root",
            str(repository),
            "--boundary",
            str(repository / SUCCESSOR_BOUNDARY_RELATIVE),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
    )
    _assert_rejected(completed, output_root)
    assert b"AUTHORITY_INVALID" in completed.stderr


def test_v2_case69_is_exact_deterministic_immutable_and_f2_bounded(
    tmp_path: Path,
) -> None:
    snapshots: list[tuple[tuple[str, bytes], ...]] = []
    for ordinal in (1, 2):
        candidate = _candidate()
        candidate_root = tmp_path / f"candidate-{ordinal}"
        output_root = tmp_path / f"output-{ordinal}"
        candidate_raw = _publish_candidate(candidate_root, candidate)
        completed = _run(candidate_root, output_root)
        assert completed.returncode == 0, completed.stderr.decode()
        assert completed.stdout == completed.stderr == b""
        assert (candidate_root / "candidate.json").read_bytes() == candidate_raw

        output = _load(BOUNDARY)["verifier_output_contract"]
        result = json.loads((output_root / "maximum_attainer.json").read_bytes())
        receipt = json.loads(
            (output_root / "verification_receipt.json").read_bytes()
        )
        witness = candidate["candidate_payload"]["witness_record"]
        assert result["witness_record"] == witness
        assert result["scope_witness_context"] == candidate["candidate_payload"][
            "scope_witness_context"
        ]
        assert result["canonical_byte_length"] == EXACT_MAXIMUM
        assert result["certified_analytic_maximum_octets"] == EXACT_MAXIMUM
        assert result["canonical_sha256"] == _sha256(_canonical_bytes(witness))
        assert result["maximum_protocol_sha256"] == SUCCESSOR_PROTOCOL_SHA256
        assert result["constraint_scope"] == "FROZEN_FIXTURE"
        assert result["constraint_scope_profile_id"] == PROFILE_ID
        assert result["required_context_object_count"] == 0
        assert result["ordered_required_context_object_ids"] == []
        certificate = result["upper_bound_certificate"]
        assert certificate["certified_upper_bound_octets"] == EXACT_MAXIMUM
        assert certificate["streamed_derivation_result_sha256"] == (
            EXPECTED_STREAM_SHA256
        )
        report = result["proof_resource_report"]
        assert report["resource_limit_catalog_id"] == SUCCESSOR_F2_ID
        assert tuple(
            row["measured_value"] for row in report["ordered_resource_measurements"]
        ) == EXPECTED_RESOURCE_VECTOR
        assert receipt["ordered_verified_context_object_entries"] == []
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
        snapshots.append(_output_snapshot(output_root))
    assert snapshots[0] == snapshots[1]


def _wrong_root_order(scope: dict[str, Any]) -> None:
    result_reference = scope["operation_result_record_reference"]
    spec_reference = scope["operation_spec_authority_reference"]
    scope["operation_result_record_reference"] = spec_reference
    scope["operation_spec_authority_reference"] = result_reference


def _wrong_spec_pointer(scope: dict[str, Any]) -> None:
    reference = scope["operation_spec_authority_reference"]
    reference["inventory_json_pointer"] = "/fixture_records/operation_specs/INGRESS"
    payload = {
        name: value
        for name, value in reference.items()
        if name != "maximum_record_reference_id"
    }
    scope["operation_spec_authority_reference"] = _record_reference(payload)


def _wrong_schedule(scope: dict[str, Any]) -> None:
    scope["ordered_application_invocations"][0]["application_name"] = (
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1"
    )


def _wrong_ordinal(scope: dict[str, Any]) -> None:
    scope["ordered_application_invocations"][0]["application_invocation_ordinal"] = 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda scope: scope.__setitem__("context_kind", "OWNER_MEMBER"),
        lambda scope: scope.__setitem__("constraint_scope_profile_id", "0" * 64),
        _wrong_root_order,
        _wrong_spec_pointer,
        _wrong_schedule,
        _wrong_ordinal,
        lambda scope: scope["ordered_application_invocations"].clear(),
    ],
    ids=[
        "context-kind",
        "profile-id",
        "root-input-order",
        "fixed-spec-pointer",
        "schedule-id",
        "invocation-ordinal",
        "missing-invocation",
    ],
)
def test_v2_rejects_resealed_context_or_schedule_substitutions(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    candidate = _candidate(mutate_scope=mutation)
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(candidate_root, candidate)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def _cross_rule_false(witness: dict[str, Any]) -> None:
    witness["result"]["final_terminal_socket_receive_call_count"] = 5


def _intrinsic_false(witness: dict[str, Any]) -> None:
    witness["result"]["ordered_terminal_ingress_read_attempt_event_ids"].append(
        "f" * 64
    )


def _nonattaining(witness: dict[str, Any]) -> None:
    witness["result"]["shutdown_trace_step_count"] = 0


@pytest.mark.parametrize(
    "mutation",
    [_cross_rule_false, _intrinsic_false, _nonattaining],
    ids=["signed-spec-p1-false", "intrinsic-p1-false", "p3-nonattainment"],
)
def test_v2_rejects_resealed_p1_or_p3_failures(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    candidate = _candidate(mutate_witness=mutation)
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(candidate_root, candidate)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_v2_keeps_context_object_files_closed_for_fixed_authority_scope(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(candidate_root, candidate)
    (candidate_root / "context_objects" / "extra.json").write_bytes(b"{}")
    _assert_rejected(_run(candidate_root, output_root), output_root)


@pytest.mark.parametrize("case_position", [435, 475])
def test_v2_keeps_later_packets_fail_closed(
    tmp_path: Path, case_position: int
) -> None:
    boundary = _load(BOUNDARY)
    seed = _load(SEED)
    case = seed["case_universe_catalog"]["ordered_case_bindings"][case_position - 1]
    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        case_position - 1
    ]
    candidate = {
        "candidate_version": boundary["candidate_bundle_contract"][
            "candidate_envelope_schema"
        ]["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": SUCCESSOR_SEED_ID,
        "finalization_manifest_id": SUCCESSOR_MANIFEST_ID,
        "case_position": case_position,
        "case_kind": case["case_kind"],
        "case_binding": copy.deepcopy(case["case_binding"]),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": (
            {
                "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
                "witness_record": {},
                "scope_witness_context": None,
                "ordered_context_object_entries": [],
            }
            if case_position == 435
            else {
                "candidate_kind": "LOCAL_SHUTDOWN_MINIMALITY_WITNESS",
                "mutated_spec": {},
                "prospective_result": {},
            }
        ),
    }
    _reseal_candidate(candidate)
    candidate_root = tmp_path / f"candidate-{case_position}"
    output_root = tmp_path / f"output-{case_position}"
    _publish_candidate(candidate_root, candidate)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_v2_source_remains_static_and_does_not_admit_later_packets() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls.isdisjoint({"__import__", "compile", "eval", "exec"})
    assert "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py" not in source
    support_lines = [
        line
        for line in source.splitlines()
        if line.startswith(("V1_SUCCESSOR_CASE_POSITIONS =", "V2_SUCCESSOR_CASE_POSITIONS ="))
    ]
    assert len(support_lines) == 1
    assert "CASE435_POSITION" not in support_lines[0]
    assert "CASE475_POSITION" not in support_lines[0]
