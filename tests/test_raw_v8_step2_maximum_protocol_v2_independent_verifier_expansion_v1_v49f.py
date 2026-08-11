"""Independent A4-P6-V1 acceptance for constructive cases 24 and 54.

The fixtures in this module are constructed from frozen public authorities;
they do not import the producer, verifier, preflight validator, or the accepted
typed runtime.  In particular, both positive witnesses attain their published
P2 endpoint by construction and hostile variants are re-sealed where relevant.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
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

SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_MANIFEST_ID = "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
SUCCESSOR_PROTOCOL_SHA256 = "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
SOURCE_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
REGISTRY_ID = "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
RULE_LITERAL_SHA256 = "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
SUCCESSOR_F2_ID = "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"

CONTEXT_OBJECT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV2V4_9F_RawV8"
)
RECORD_REFERENCE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8"
)

EXPECTED = {
    24: {
        "maximum": 523_738,
        "plan_id": "428ff735837b841e66103d64cbcd4af7ceaf88d009c38229ad5e4cde0ab30d67",
        "resource_vector": (
            1, 2_101_277, 39, 459, 4_202_945, 5, 39, 26_493, 340_068,
            362_505, 488_331, 1, 0, 0, 6, 32, 36_304, 9_469,
        ),
        "stream_sha256": "bf6a4886b3bc7110a61a5170e2b03f5de402a08e5bd78eccafb54b719d99cbcd",
    },
    54: {
        "maximum": 3_145_728,
        "plan_id": "4eeedde2c223693e62a2b89a2016b43f9954496771189616ad68ac8cf21e6da1",
        "resource_vector": (
            1, 515, 5, 9, 1_031, 1, 5, 3_415, 9_775, 12_712,
            41_372, 1, 0, 0, 4, 9, 3_937, 1_589,
        ),
        "stream_sha256": "9a9b153f3fee7073849416c8ccc3f419bda471b1c541165b20f49989cb6b379f",
    },
}


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


def _case_and_plan(case_position: int) -> tuple[dict[str, Any], dict[str, Any]]:
    seed = _load(SEED)
    case = next(
        row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
        if row["case_position"] == case_position
    )
    plan = next(
        row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
        if row["case_position"] == case_position
    )
    if case_position in EXPECTED:
        assert plan["logical_count_plan_id"] == EXPECTED[case_position]["plan_id"]
    return case, plan


def _reseal_owner(owner: dict[str, Any]) -> None:
    payload = {
        name: owner[name]
        for name in (
            "candidate_id",
            "attempt_id",
            "operation_kind",
            "result_type",
            "result",
        )
    }
    owner["result_evidence_id"] = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": owner["canonicalization_version"],
                "domain": owner["record_domain"],
                "payload": payload,
                "schema_version": owner["measurement_schema_version"],
            }
        )
    )


def _case24_witness() -> dict[str, Any]:
    inventory = _load(INVENTORY)
    owner = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    witness = owner["result"]
    arrays = (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
        "ordered_terminal_parser_transition_event_ids",
    )
    free_integers = (
        "shutdown_trace_step_count",
        "final_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count",
        "final_terminal_tls_record_count",
        "final_terminal_tls_unwrap_iteration_count",
        "final_terminal_zero_progress_iteration_count",
        "final_terminal_ingress_automatic_output_count",
        "final_websocket_send_attempt_count",
        "final_tls_control_send_attempt_count",
    )

    # The five non-empty arrays contribute 67 octets per additional SHA item.
    # Eight 16-digit values and one 5-digit value close the 124-octet residue.
    for position, name in enumerate(free_integers):
        witness[name] = (
            9_007_199_254_740_991
            if position < 8
            else (10_000 if position == 8 else 0)
        )
    witness["final_peer_shutdown_poll_count"] = 0
    witness["final_terminal_ingress_batch_count"] = 924
    witness["final_terminal_ingress_parser_unit_count"] = 4_095
    values = [f"{position:064x}" for position in range(4_095)]
    witness[arrays[0]] = values[:924]
    witness[arrays[1]] = values[:924]
    witness[arrays[2]] = values[:924]
    witness[arrays[3]] = values[:924]
    witness[arrays[4]] = values
    assert len(_canonical_bytes(witness)) == EXPECTED[24]["maximum"]
    return witness


def _case54_witness() -> dict[str, Any]:
    witness = {
        "vocabulary_id": "v",
        "members": [f"a{position:03d}" for position in range(511)] + ["z"],
    }
    deficit = EXPECTED[54]["maximum"] - len(_canonical_bytes(witness))
    witness["members"][-1] = "z" * (deficit + 1)
    assert len(witness["members"]) == 512
    assert all(
        left < right
        for left, right in zip(witness["members"], witness["members"][1:])
    )
    assert len(_canonical_bytes(witness)) == EXPECTED[54]["maximum"]
    return witness


def _owner_context(
    witness: dict[str, Any],
    mutate_owner: Callable[[dict[str, Any]], None] | None = None,
    reseal_owner: bool = True,
) -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any]]:
    inventory = _load(INVENTORY)
    owner = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    owner["result"] = copy.deepcopy(witness)
    if mutate_owner is not None:
        mutate_owner(owner)
    if reseal_owner:
        _reseal_owner(owner)
    raw = _canonical_bytes(owner)
    raw_sha = _sha256(raw)
    context_payload = {
        "maximum_protocol_sha256": SUCCESSOR_PROTOCOL_SHA256,
        "source_inventory_sha256": SOURCE_INVENTORY_ID,
        "external_schema_registry_id": REGISTRY_ID,
        "rule_literal_authority_sha256": RULE_LITERAL_SHA256,
        "record_type_name": "CapacityMeasurementOperationResultEvidence",
        "record_identity_field": "result_evidence_id",
        "record_identity": owner["result_evidence_id"],
        "record_canonical_byte_length": len(raw),
        "record_canonical_sha256": raw_sha,
        "record": owner,
    }
    object_id = _seed_semantic_id(CONTEXT_OBJECT_DOMAIN, context_payload)
    relative = f"context_objects/{object_id[:2]}/{object_id}.json"
    entry = {
        "context_object_position": 1,
        "claimed_maximum_context_object_id": object_id,
        "record_type_name": "CapacityMeasurementOperationResultEvidence",
        "repository_relative_path": relative,
        "raw_octet_count": len(raw),
        "raw_sha256": raw_sha,
    }
    reference_payload = {
        "reference_kind": "CONTEXT_OBJECT",
        "maximum_context_object_id": object_id,
        "record_type_name": "CapacityMeasurementOperationResultEvidence",
        "record_identity_field": "result_evidence_id",
        "record_identity": owner["result_evidence_id"],
        "record_canonical_byte_length": len(raw),
        "record_canonical_sha256": raw_sha,
    }
    reference = dict(reference_payload)
    reference["maximum_record_reference_id"] = _seed_semantic_id(
        RECORD_REFERENCE_DOMAIN, reference_payload
    )
    scope = {
        "context_kind": "OWNER_MEMBER",
        "owner_record_reference": reference,
        "payload_typed_member_path": ["result"],
    }
    return entry, {relative: raw}, scope


def _reseal_candidate(candidate: dict[str, Any]) -> None:
    schema = _load(BOUNDARY)["candidate_bundle_contract"]["candidate_envelope_schema"]
    payload = {name: candidate[name] for name in schema["ordered_member_names"][:-1]}
    candidate["constructive_candidate_id"] = _semantic_id(
        schema["identity_domain"], payload
    )


def _candidate(
    case_position: int,
    mutate_witness: Callable[[dict[str, Any]], None] | None = None,
    mutate_owner: Callable[[dict[str, Any]], None] | None = None,
    reseal_owner: bool = True,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    boundary = _load(BOUNDARY)
    case, plan = _case_and_plan(case_position)
    witness = _case24_witness() if case_position == 24 else _case54_witness()
    if mutate_witness is not None:
        mutate_witness(witness)
    if case_position == 24:
        entry, contexts, scope = _owner_context(
            witness, mutate_owner=mutate_owner, reseal_owner=reseal_owner
        )
        entries = [entry]
    else:
        contexts, scope, entries = {}, None, []
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
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": witness,
            "scope_witness_context": scope,
            "ordered_context_object_entries": entries,
        },
    }
    _reseal_candidate(candidate)
    return candidate, contexts


def _publish_candidate(
    root: Path, candidate: dict[str, Any], contexts: dict[str, bytes]
) -> tuple[bytes, dict[str, bytes]]:
    root.mkdir(mode=0o700)
    (root / "context_objects").mkdir(mode=0o700)
    raw = _pretty_bytes(candidate)
    (root / "candidate.json").write_bytes(raw)
    for relative, context_raw in contexts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(context_raw)
    return raw, dict(contexts)


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


def _output_snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_v1_source_preserves_static_independence_and_pinned_runtime_barrier() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls.isdisjoint({"__import__", "compile", "eval", "exec"})
    assert "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py" not in source
    assert "validate_raw_v8_step2_external_schema_v2_maximum_protocol_v49f.py" not in source
    assert "TYPED_RULE_RUNTIME_SHA256" in source
    assert "typed_runtime_raw = _load_additional_authority" in source


@pytest.mark.parametrize("case_position", [24, 54])
def test_v1_attainers_are_exact_deterministic_immutable_and_f2_bounded(
    tmp_path: Path, case_position: int
) -> None:
    snapshots: list[tuple[tuple[str, bytes], ...]] = []
    for ordinal in (1, 2):
        candidate, contexts = _candidate(case_position)
        candidate_root = tmp_path / f"candidate-{case_position}-{ordinal}"
        output_root = tmp_path / f"output-{case_position}-{ordinal}"
        candidate_raw, context_raws = _publish_candidate(
            candidate_root, candidate, contexts
        )
        completed = _run(candidate_root, output_root)
        assert completed.returncode == 0, completed.stderr.decode()
        assert completed.stdout == completed.stderr == b""
        assert (candidate_root / "candidate.json").read_bytes() == candidate_raw
        for relative, raw in context_raws.items():
            assert (candidate_root / relative).read_bytes() == raw
            assert (output_root / relative).read_bytes() == raw

        boundary = _load(BOUNDARY)
        output = boundary["verifier_output_contract"]
        result = json.loads((output_root / "maximum_attainer.json").read_bytes())
        receipt = json.loads(
            (output_root / "verification_receipt.json").read_bytes()
        )
        witness_raw = _canonical_bytes(candidate["candidate_payload"]["witness_record"])
        assert len(witness_raw) == EXPECTED[case_position]["maximum"]
        assert result["witness_record"] == candidate["candidate_payload"]["witness_record"]
        assert result["scope_witness_context"] == candidate["candidate_payload"]["scope_witness_context"]
        assert result["canonical_byte_length"] == len(witness_raw)
        assert result["certified_analytic_maximum_octets"] == len(witness_raw)
        assert result["canonical_sha256"] == _sha256(witness_raw)
        assert result["maximum_protocol_sha256"] == SUCCESSOR_PROTOCOL_SHA256
        certificate = result["upper_bound_certificate"]
        assert certificate["certified_upper_bound_octets"] == len(witness_raw)
        assert certificate["streamed_derivation_result_sha256"] == EXPECTED[case_position]["stream_sha256"]
        report = result["proof_resource_report"]
        assert report["resource_limit_catalog_id"] == SUCCESSOR_F2_ID
        assert tuple(
            row["measured_value"]
            for row in report["ordered_resource_measurements"]
        ) == EXPECTED[case_position]["resource_vector"]
        assert receipt["ordered_verified_context_object_entries"] == candidate[
            "candidate_payload"
        ]["ordered_context_object_entries"]
        assert result["ordered_required_context_object_ids"] == [
            row["claimed_maximum_context_object_id"]
            for row in candidate["candidate_payload"]["ordered_context_object_entries"]
        ]
        if case_position == 24:
            assert candidate["candidate_payload"]["ordered_context_object_entries"][0][
                "raw_octet_count"
            ] == 524_287
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


@pytest.mark.parametrize(
    ("case_position", "mutation"),
    [
        (
            24,
            lambda witness: witness[
                "ordered_terminal_ingress_read_attempt_event_ids"
            ].__setitem__(1, witness["ordered_terminal_ingress_read_attempt_event_ids"][0]),
        ),
        (
            24,
            lambda witness: witness.__setitem__(
                "final_terminal_ingress_batch_count", 923
            ),
        ),
        (
            24,
            lambda witness: witness.__setitem__("shutdown_trace_step_count", 0),
        ),
        (
            54,
            lambda witness: witness["members"].__setitem__(1, witness["members"][0]),
        ),
        (
            54,
            lambda witness: witness["members"].__setitem__(
                1, witness["members"][0][::-1]
            ),
        ),
        (54, lambda witness: witness["members"].__setitem__(-1, "z")),
    ],
    ids=[
        "case24-duplicate-array-item",
        "case24-intrinsic-count-mismatch",
        "case24-nonattainment",
        "case54-duplicate-member",
        "case54-reordered-member",
        "case54-nonattainment",
    ],
)
def test_v1_rejects_resealed_illegal_or_nonattaining_witnesses(
    tmp_path: Path,
    case_position: int,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    candidate, contexts = _candidate(case_position, mutation)
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(candidate_root, candidate, contexts)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_v1_rejects_owner_witness_divergence_and_context_tamper(tmp_path: Path) -> None:
    candidate, contexts = _candidate(24)
    candidate["candidate_payload"]["witness_record"][
        "terminal_outcome"
    ] = "FATAL"
    _reseal_candidate(candidate)
    candidate_root = tmp_path / "divergent-candidate"
    output_root = tmp_path / "divergent-output"
    _publish_candidate(candidate_root, candidate, contexts)
    _assert_rejected(_run(candidate_root, output_root), output_root)

    candidate, contexts = _candidate(24)
    relative = next(iter(contexts))
    contexts[relative] = contexts[relative][:-1] + b" "
    candidate_root = tmp_path / "tampered-candidate"
    output_root = tmp_path / "tampered-output"
    _publish_candidate(candidate_root, candidate, contexts)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_v1_rejects_extra_or_missing_context_closure(tmp_path: Path) -> None:
    for label, mutation in (
        ("missing", "missing"),
        ("extra", "extra"),
    ):
        candidate, contexts = _candidate(24)
        if mutation == "missing":
            contexts.clear()
        candidate_root = tmp_path / f"candidate-{label}"
        output_root = tmp_path / f"output-{label}"
        _publish_candidate(candidate_root, candidate, contexts)
        if mutation == "extra":
            (candidate_root / "context_objects" / "extra.json").write_bytes(b"{}")
        _assert_rejected(_run(candidate_root, output_root), output_root)


@pytest.mark.parametrize(
    ("label", "mutation", "reseal_owner"),
    [
        (
            "wrong-discriminator",
            lambda owner: owner.__setitem__("operation_kind", "INGRESS"),
            True,
        ),
        (
            "wrong-owner-identity",
            lambda owner: owner.__setitem__("result_evidence_id", "0" * 64),
            False,
        ),
    ],
)
def test_v1_rejects_internally_referenced_illegal_owner_records(
    tmp_path: Path,
    label: str,
    mutation: Callable[[dict[str, Any]], None],
    reseal_owner: bool,
) -> None:
    candidate, contexts = _candidate(
        24, mutate_owner=mutation, reseal_owner=reseal_owner
    )
    candidate_root = tmp_path / f"candidate-{label}"
    output_root = tmp_path / f"output-{label}"
    _publish_candidate(candidate_root, candidate, contexts)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def _overflow_case24(witness: dict[str, Any]) -> None:
    witness["ordered_terminal_parser_transition_event_ids"].append(f"{4095:064x}")
    witness["final_terminal_ingress_parser_unit_count"] = 4_096


@pytest.mark.parametrize(
    ("case_position", "mutation"),
    [
        (24, _overflow_case24),
        (54, lambda witness: witness["members"].__setitem__(-1, witness["members"][-1] + "z")),
    ],
    ids=["case24-owner-codec-overflow", "case54-self-codec-overflow"],
)
def test_v1_rejects_legal_shape_above_the_frozen_codec_endpoint(
    tmp_path: Path,
    case_position: int,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    candidate, contexts = _candidate(case_position, mutation)
    candidate_root = tmp_path / f"candidate-{case_position}"
    output_root = tmp_path / f"output-{case_position}"
    _publish_candidate(candidate_root, candidate, contexts)
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_v1_rejects_malformed_utf8_before_semantic_acceptance(tmp_path: Path) -> None:
    candidate, contexts = _candidate(54)
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(candidate_root, candidate, contexts)
    path = candidate_root / "candidate.json"
    raw = path.read_bytes()
    assert b'"a000"' in raw
    path.write_bytes(raw.replace(b'"a000"', b'"\xff000"', 1))
    _assert_rejected(_run(candidate_root, output_root), output_root)


@pytest.mark.parametrize("case_position", [69, 435, 475])
def test_v1_keeps_later_packets_fail_closed(
    tmp_path: Path, case_position: int
) -> None:
    boundary = _load(BOUNDARY)
    case, plan = _case_and_plan(case_position)
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
            if case_position != 475
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
    _publish_candidate(candidate_root, candidate, {})
    _assert_rejected(_run(candidate_root, output_root), output_root)
