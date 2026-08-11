"""Independent A4-P6-V4 acceptance for local-minimality case 475.

The fixture reconstructs the one-field mutation and complete prospective result
from the frozen V4 inventory without importing the verifier.  The verifier must
execute the local controller, P1, masked-domain P2/P3, event meter, identities,
and publication itself; candidate bytes remain untrusted data.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import pathlib
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
BOUNDARY = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
SUCCESSOR_BOUNDARY = ROOT / (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
PACKED_BOUNDARY = ROOT / (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
INVENTORY = ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json"
REGISTRY = ROOT / (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)

CASE_POSITION = 475
EXACT_MAXIMUM = 524_380
PREDECESSOR_MAXIMUM = 524_112
WINNING_MEMBER = "maximum_terminal_ingress_batches"
WINNING_VALUE = 1_948
WINNING_DELTA = 1_947
PLAN_ID = "2d46a1b71c9466fd3268b93dbc3e4a62a4855dd0324f4cfecfbb60d4589bbbc0"
PROFILE_ID = "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
BASELINE_SPEC_ID = "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
MUTATED_SPEC_ID = "572155284c3b8b0852b406d5cbce662aba7579180f89ee3740a6c86ede66f16a"
SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_MANIFEST_ID = "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
SUCCESSOR_PROTOCOL_SHA256 = "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
SUCCESSOR_F2_ID = "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
SOURCE_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
CANDIDATE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2ConstructiveCandidateEnvelopeV1V4_9F_RawV8"
)
LOCAL_SCOPE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownProofScopeV2V4_9F_RawV8"
)
MINIMALITY_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMinimalityCertificateV2"
    "V4_9F_RawV8"
)
EXPECTED_STREAM_SHA256 = "5f2f61d0f9f09174d3bb17288c02f36d9ec7ec358468d36ed19a2e44958cbbb3"
EXPECTED_CANDIDATE_ID = "ee38407312f872f0d8dc3f5d6b3ebe9990f294ce245b406ba3e33cce243dcb42"
EXPECTED_CANDIDATE_OCTETS = 614_566
EXPECTED_CANDIDATE_SHA256 = "bdf7f8e4213cbf51b70b2dac0bdc97ffd1d55304b37bd3d20b8b9d54ba7977dc"
EXPECTED_PROSPECTIVE_RESULT_ID = "8a22dfcb61a9e083c2edccc7902d0e4e414c8be4d130570a495b1cdecb1a014c"
EXPECTED_LOCAL_SCOPE_ID = "4db3b0d60c9487e2b0913cf54fc05fa88ee5cac9e7aa979b3c97d6d46d1974b1"
EXPECTED_UPPER_CERTIFICATE_ID = "bc4594ce40f5ba4d80276ae1eec89c34f2e9eaff8328834093fa1e2cfa4dd118"
EXPECTED_EXCLUSION_SHA256 = "4cf7a46c0488d044368be412db5f837be5b4bd8f5c71907df83271d89d5cceb9"
EXPECTED_MINIMALITY_CERTIFICATE_ID = "62c6c97f9af5a8f4924f45a4c4e2d144d93eb17cd84d5b17b0cd06af6eb15792"
EXPECTED_RESOURCE_REPORT_ID = "ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8"
EXPECTED_RESULT_ID = "937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73"
EXPECTED_RESULT_OCTETS = 604_156
EXPECTED_RESULT_SHA256 = "a1e1316c970e60db198d8775eeb89a1e0eb7e4cdda5ddca64f54c666130fb7f8"
EXPECTED_RECEIPT_ID = "eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f"
EXPECTED_RECEIPT_OCTETS = 3_173
EXPECTED_RECEIPT_SHA256 = "93b1ab8dc2fdbbd8dadabae5bd5591f8129d0ce2611f6bb1d25e74f46078f5b2"
EXPECTED_RESOURCE_VECTOR = (
    1,
    11,
    12,
    11,
    11,
    0,
    12,
    9_591,
    20_047,
    28_612,
    49_103,
    4,
    1,
    1,
    1,
    11,
    18_156,
    672,
)


def _load(path: pathlib.Path) -> dict[str, Any]:
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


def _descriptors() -> dict[str, dict[str, Any]]:
    return {
        row["type_name"]: row
        for row in _load(REGISTRY)["ordered_external_type_descriptors"]
    }


def _reseal_typed_record(record: dict[str, Any], type_name: str) -> None:
    descriptor = _descriptors()[type_name]
    identity_field = descriptor["identity_field"]
    assert isinstance(identity_field, str)
    payload = {
        name: record[name]
        for name in descriptor["identity_payload_member_order"]
    }
    record[identity_field] = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": record["canonicalization_version"],
                "domain": descriptor["described_record_domain"],
                "payload": payload,
                "schema_version": record["measurement_schema_version"],
            }
        )
    )


def _reseal_candidate(candidate: dict[str, Any]) -> None:
    payload = {
        name: value
        for name, value in candidate.items()
        if name != "constructive_candidate_id"
    }
    candidate["constructive_candidate_id"] = _semantic_id(
        CANDIDATE_DOMAIN, payload
    )


def _attainer_result(
    baseline_result: dict[str, Any], signed_spec: dict[str, Any], batch_count: int
) -> dict[str, Any]:
    result = copy.deepcopy(baseline_result)
    body = result["result"]
    batch_arrays = (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
    )
    values = [f"{ordinal:064x}" for ordinal in range(batch_count)]
    for name in batch_arrays:
        body[name] = values.copy()
    parser_count = signed_spec["spec"]["maximum_terminal_ingress_parser_units"]
    body["ordered_terminal_parser_transition_event_ids"] = [
        f"{ordinal:064x}" for ordinal in range(parser_count)
    ]
    for position, name in enumerate(
        (
            "local_close_dispatch_completion_event_id",
            "local_shutdown_deadline_evidence_event_id",
            "websocket_close_received_transition_event_id",
        ),
        1,
    ):
        body[name] = f"{position:064x}"
    body["shutdown_trace_step_count"] = 9_007_199_254_740_991
    counter_map = {
        "maximum_terminal_ingress_batches": "final_terminal_ingress_batch_count",
        "maximum_terminal_ingress_ciphertext_octets": "final_terminal_ingress_ciphertext_octets",
        "maximum_terminal_ingress_plaintext_octets": "final_terminal_ingress_plaintext_octets",
        "maximum_terminal_socket_receive_calls": "final_terminal_socket_receive_call_count",
        "maximum_terminal_tls_records": "final_terminal_tls_record_count",
        "maximum_terminal_tls_unwrap_iterations": "final_terminal_tls_unwrap_iteration_count",
        "maximum_terminal_zero_progress_iterations": "final_terminal_zero_progress_iteration_count",
        "maximum_terminal_ingress_parser_units": "final_terminal_ingress_parser_unit_count",
        "maximum_terminal_ingress_automatic_outputs": "final_terminal_ingress_automatic_output_count",
        "maximum_websocket_send_attempts": "final_websocket_send_attempt_count",
        "maximum_tls_control_send_attempts": "final_tls_control_send_attempt_count",
        "maximum_peer_shutdown_polls": "final_peer_shutdown_poll_count",
    }
    for spec_name, result_name in counter_map.items():
        body[result_name] = signed_spec["spec"][spec_name]
    _reseal_typed_record(result, "CapacityMeasurementOperationResultEvidence")
    return result


@pytest.fixture(scope="session")
def local_candidate() -> dict[str, Any]:
    boundary = _load(BOUNDARY)
    seed = _load(SEED)
    inventory = _load(INVENTORY)
    case = seed["case_universe_catalog"]["ordered_case_bindings"][CASE_POSITION - 1]
    plan = seed["logical_plan_recipe_catalog"][
        "ordered_logical_count_plan_records"
    ][CASE_POSITION - 1]
    baseline_spec = copy.deepcopy(
        inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    )
    mutated_spec = copy.deepcopy(baseline_spec)
    mutated_spec["spec"][WINNING_MEMBER] = WINNING_VALUE
    _reseal_typed_record(mutated_spec, "CapacityMeasurementOperationSpec")
    assert mutated_spec["operation_spec_id"] == MUTATED_SPEC_ID
    prospective = _attainer_result(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"],
        mutated_spec,
        WINNING_VALUE,
    )
    assert len(_canonical_bytes(prospective)) == EXACT_MAXIMUM
    assert prospective["result_evidence_id"] == EXPECTED_PROSPECTIVE_RESULT_ID
    candidate = {
        "candidate_version": boundary["candidate_bundle_contract"]
        ["candidate_envelope_schema"]["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": SUCCESSOR_SEED_ID,
        "finalization_manifest_id": SUCCESSOR_MANIFEST_ID,
        "case_position": CASE_POSITION,
        "case_kind": case["case_kind"],
        "case_binding": case["case_binding"],
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "LOCAL_SHUTDOWN_MUTATION",
            "mutated_spec": mutated_spec,
            "prospective_result": prospective,
        },
    }
    _reseal_candidate(candidate)
    assert candidate["constructive_candidate_id"] == EXPECTED_CANDIDATE_ID
    assert len(_pretty_bytes(candidate)) == EXPECTED_CANDIDATE_OCTETS
    assert _sha256(_pretty_bytes(candidate)) == EXPECTED_CANDIDATE_SHA256
    return candidate


def _publish_candidate(
    root: pathlib.Path, candidate: dict[str, Any], *, extra_context: bool = False
) -> pathlib.Path:
    root.mkdir(parents=True)
    context = root / "context_objects"
    context.mkdir()
    if extra_context:
        (context / "extra.json").write_bytes(b"{}")
    (root / "candidate.json").write_bytes(_pretty_bytes(candidate))
    return root


def _run(
    candidate_root: pathlib.Path,
    output_root: pathlib.Path,
    *,
    boundary: pathlib.Path = PACKED_BOUNDARY,
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
            str(boundary),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        check=False,
        capture_output=True,
    )


def _snapshot(root: pathlib.Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    )


def _assert_rejected(
    tmp_path: pathlib.Path,
    candidate: dict[str, Any],
    *,
    boundary: pathlib.Path = PACKED_BOUNDARY,
    extra_context: bool = False,
) -> None:
    candidate_root = _publish_candidate(
        tmp_path / "candidate", candidate, extra_context=extra_context
    )
    before = _snapshot(candidate_root)
    completed = _run(candidate_root, tmp_path / "output", boundary=boundary)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"
    )
    assert not (tmp_path / "output").exists()
    assert _snapshot(candidate_root) == before


def test_case475_is_exact_deterministic_immutable_and_f2_bounded(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    snapshots = []
    for name in ("first", "second"):
        candidate_root = _publish_candidate(
            tmp_path / name / "candidate", copy.deepcopy(local_candidate)
        )
        before = _snapshot(candidate_root)
        output_root = tmp_path / name / "output"
        completed = _run(candidate_root, output_root)
        assert completed.returncode == 0, completed.stderr.decode()
        assert completed.stdout == completed.stderr == b""
        assert _snapshot(candidate_root) == before
        snapshots.append(_snapshot(output_root))
    assert snapshots[0] == snapshots[1]
    assert [name for name, _ in snapshots[0]] == [
        "local_shutdown_unrepresentable.json",
        "verification_receipt.json",
    ]

    output = dict(snapshots[0])
    assert len(output["local_shutdown_unrepresentable.json"]) == EXPECTED_RESULT_OCTETS
    assert _sha256(output["local_shutdown_unrepresentable.json"]) == EXPECTED_RESULT_SHA256
    assert len(output["verification_receipt.json"]) == EXPECTED_RECEIPT_OCTETS
    assert _sha256(output["verification_receipt.json"]) == EXPECTED_RECEIPT_SHA256
    result = json.loads(output["local_shutdown_unrepresentable.json"])
    receipt = json.loads(output["verification_receipt.json"])
    assert result["mutated_spec"] == local_candidate["candidate_payload"]["mutated_spec"]
    assert result["prospective_result"] == local_candidate["candidate_payload"][
        "prospective_result"
    ]
    assert result["prospective_result_canonical_byte_length"] == EXACT_MAXIMUM
    assert result["changed_limit_field_count"] == 1
    assert result["sum_absolute_integer_deltas"] == WINNING_DELTA
    assert result["mutated_limit_members"] == [
        {
            "domain_position": 1,
            "member_name": WINNING_MEMBER,
            "baseline_value": 1,
            "mutated_value": WINNING_VALUE,
            "absolute_delta": WINNING_DELTA,
        }
    ]
    assert result["expected_rejection_coordinate"] == {
        "record_type_name": "CapacityMeasurementOperationResultEvidence",
        "typed_member_path": [],
        "validation_layer": "CODEC_BOUND",
        "codec_byte_bound_relation": "LT",
        "codec_octet_limit": 524_288,
        "observed_canonical_byte_length": EXACT_MAXIMUM,
        "failure_class": "CODEC_OCTET_LIMIT_VIOLATION",
    }
    scope_payload = {
        "maximum_protocol_sha256": SUCCESSOR_PROTOCOL_SHA256,
        "source_inventory_sha256": SOURCE_INVENTORY_ID,
        "constraint_scope_profile_id": PROFILE_ID,
        "baseline_operation_spec_id": BASELINE_SPEC_ID,
        "mutated_operation_spec_id": MUTATED_SPEC_ID,
    }
    scope_id = _semantic_id(LOCAL_SCOPE_DOMAIN, scope_payload)
    assert scope_id == EXPECTED_LOCAL_SCOPE_ID
    certificate = result["minimality_certificate"]
    assert "minimality_certificate_id" not in certificate
    assert certificate["local_shutdown_proof_scope_id"] == scope_id
    assert certificate["winning_objective"] == {
        "changed_limit_field_count": 1,
        "sum_absolute_integer_deltas": WINNING_DELTA,
        "changed_member_names_in_lexical_order": [WINNING_MEMBER],
        "resulting_changed_values_in_that_same_order": [WINNING_VALUE],
    }
    certificate_payload = {
        name: value
        for name, value in certificate.items()
        if name != "local_shutdown_minimality_certificate_id"
    }
    assert certificate["local_shutdown_minimality_certificate_id"] == _semantic_id(
        MINIMALITY_DOMAIN, certificate_payload
    )
    assert certificate["local_shutdown_minimality_certificate_id"] == (
        EXPECTED_MINIMALITY_CERTIFICATE_ID
    )
    assert certificate["better_objective_exclusion_result_sha256"] == (
        EXPECTED_EXCLUSION_SHA256
    )
    bound = certificate["winning_prospective_bound_certificate"]
    assert bound["upper_bound_certificate_id"] == EXPECTED_UPPER_CERTIFICATE_ID
    assert bound["certified_upper_bound_octets"] == EXACT_MAXIMUM
    assert bound["streamed_derivation_result_sha256"] == EXPECTED_STREAM_SHA256
    report = result["proof_resource_report"]
    assert report["resource_limit_catalog_id"] == SUCCESSOR_F2_ID
    assert report["derivation_scope_id"] == scope_id
    assert report["derivation_certificate_id"] == certificate[
        "local_shutdown_minimality_certificate_id"
    ]
    assert tuple(
        row["measured_value"] for row in report["ordered_resource_measurements"]
    ) == EXPECTED_RESOURCE_VECTOR
    assert report["proof_resource_report_id"] == EXPECTED_RESOURCE_REPORT_ID
    manifest = _load(
        ROOT
        / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
    )
    assert all(
        measured <= limit["f2_per_case"]
        for measured, limit in zip(
            EXPECTED_RESOURCE_VECTOR,
            manifest["ordered_f2_limit_records"],
            strict=True,
        )
    )
    boundary = _load(BOUNDARY)
    schema = boundary["verifier_output_contract"]["local_shutdown_result_schema"]
    assert result["local_shutdown_unrepresentable_id"] == _semantic_id(
        schema["identity_domain"],
        {
            name: result[name]
            for name in schema["ordered_member_names"][:-1]
        },
    )
    assert result["local_shutdown_unrepresentable_id"] == EXPECTED_RESULT_ID
    assert receipt["verification_status"] == "LOCAL_MINIMALITY_ACCEPTED"
    assert receipt["result_artifact_kind"] == "LOCAL_SHUTDOWN_RESULT"
    assert receipt["result_artifact_id"] == result[
        "local_shutdown_unrepresentable_id"
    ]
    assert receipt["ordered_verified_context_object_entries"] == []
    assert receipt["verification_receipt_id"] == EXPECTED_RECEIPT_ID


@pytest.mark.parametrize("value", [1, 1_947, 1_949])
def test_case475_rejects_equal_predecessor_or_wrong_winning_mutation(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any], value: int
) -> None:
    candidate = copy.deepcopy(local_candidate)
    spec = candidate["candidate_payload"]["mutated_spec"]
    spec["spec"][WINNING_MEMBER] = value
    _reseal_typed_record(spec, "CapacityMeasurementOperationSpec")
    _reseal_candidate(candidate)
    _assert_rejected(tmp_path, candidate)


def test_case475_rejects_a_resealed_multi_field_mutation(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    candidate = copy.deepcopy(local_candidate)
    spec = candidate["candidate_payload"]["mutated_spec"]
    spec["spec"]["maximum_terminal_socket_receive_calls"] += 1
    _reseal_typed_record(spec, "CapacityMeasurementOperationSpec")
    _reseal_candidate(candidate)
    _assert_rejected(tmp_path, candidate)


def _nonattaining(candidate: dict[str, Any]) -> None:
    payload = candidate["candidate_payload"]
    inventory = _load(INVENTORY)
    payload["prospective_result"] = _attainer_result(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"],
        payload["mutated_spec"],
        WINNING_VALUE - 1,
    )
    payload["prospective_result"]["result"][
        "final_terminal_ingress_batch_count"
    ] = WINNING_VALUE - 1
    _reseal_typed_record(
        payload["prospective_result"],
        "CapacityMeasurementOperationResultEvidence",
    )


def _p1_false(candidate: dict[str, Any]) -> None:
    result = candidate["candidate_payload"]["prospective_result"]
    result["result"]["terminal_outcome"] = "FATAL"
    _reseal_typed_record(result, "CapacityMeasurementOperationResultEvidence")


def _malformed_nested_sha(candidate: dict[str, Any]) -> None:
    result = candidate["candidate_payload"]["prospective_result"]
    result["result"]["ordered_terminal_ingress_read_attempt_event_ids"][0] = "g" * 64
    _reseal_typed_record(result, "CapacityMeasurementOperationResultEvidence")


def _stale_result_identity(candidate: dict[str, Any]) -> None:
    candidate["candidate_payload"]["prospective_result"]["result"][
        "final_terminal_ingress_batch_count"
    ] -= 1


@pytest.mark.parametrize(
    "mutator",
    [_nonattaining, _p1_false, _malformed_nested_sha, _stale_result_identity],
    ids=["nonattaining", "p1-false", "malformed-nested-sha", "stale-identity"],
)
def test_case475_rejects_resealed_prospective_result_substitutions(
    tmp_path: pathlib.Path,
    local_candidate: dict[str, Any],
    mutator: Callable[[dict[str, Any]], None],
) -> None:
    candidate = copy.deepcopy(local_candidate)
    mutator(candidate)
    _reseal_candidate(candidate)
    _assert_rejected(tmp_path, candidate)


def test_case475_rejects_a_resealed_producer_proof_claim(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    candidate = copy.deepcopy(local_candidate)
    candidate["candidate_payload"]["upper_bound_certificate"] = {}
    _reseal_candidate(candidate)
    _assert_rejected(tmp_path, candidate)


def test_case475_rejects_a_resealed_wrong_payload_tag(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    candidate = copy.deepcopy(local_candidate)
    candidate["candidate_payload"]["candidate_kind"] = "MAXIMUM_WITNESS_CONTEXT"
    _reseal_candidate(candidate)
    _assert_rejected(tmp_path, candidate)


def test_case475_requires_the_packed_successor_authority_mode(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    _assert_rejected(tmp_path, copy.deepcopy(local_candidate), boundary=SUCCESSOR_BOUNDARY)


def test_case475_rejects_predecessor_authority_ids(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    _assert_rejected(tmp_path, copy.deepcopy(local_candidate), boundary=BOUNDARY)


def test_case475_requires_an_empty_context_root(
    tmp_path: pathlib.Path, local_candidate: dict[str, Any]
) -> None:
    _assert_rejected(tmp_path, copy.deepcopy(local_candidate), extra_context=True)


def test_v4_source_is_static_and_isolated_from_producers_and_proof_checkers() -> None:
    tree = ast.parse(VERIFIER.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (
            node.names
            if isinstance(node, ast.Import)
            else [ast.alias(name=node.module or "")]
        )
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert imports <= {
        "hashlib",
        "json",
        "os",
        "pathlib",
        "stat",
        "sys",
        "tempfile",
    }
    assert imports.isdisjoint({"riskyieldmm", "scripts", "tests", "importlib"})
    assert "spec_from_file_location" not in calls


def test_case475_fixture_pins_the_predecessor_boundary() -> None:
    inventory = _load(INVENTORY)
    baseline = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    assert baseline["operation_spec_id"] == BASELINE_SPEC_ID
    candidate_spec = copy.deepcopy(baseline)
    candidate_spec["spec"][WINNING_MEMBER] = WINNING_VALUE - 1
    _reseal_typed_record(candidate_spec, "CapacityMeasurementOperationSpec")
    predecessor = _attainer_result(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"],
        candidate_spec,
        WINNING_VALUE - 1,
    )
    assert len(_canonical_bytes(predecessor)) == PREDECESSOR_MAXIMUM
