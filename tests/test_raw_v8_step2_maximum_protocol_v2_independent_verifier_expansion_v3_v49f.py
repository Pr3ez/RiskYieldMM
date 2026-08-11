"""Independent A4-P6-V3 acceptance for exact packed-context case 435.

The expensive positive fixture is reconstructed once from the accepted C2
attainer constructor and then presented only as untrusted candidate bytes.  The
verifier imports neither that constructor nor any C1/C2/C3 checker/certificate;
it must independently resolve the corrected authority chain, unpack and
validate every complete record, replay P1, measure P3, and enforce F2.

The generic typed runtime is intentionally absent from the verifier.  A
separate differential test compares the verifier-owned closed case-435 rule
subset with that pinned runtime.
"""

from __future__ import annotations

import ast
import copy
import functools
import hashlib
import importlib.util
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
PACKED_BOUNDARY = ROOT / (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
SUCCESSOR_BOUNDARY = ROOT / (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
SEED_DELTA = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
INVENTORY = ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json"
REGISTRY = ROOT / (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
MANIFEST = ROOT / (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
C2_CONSTRUCTOR = ROOT / (
    "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py"
)

CASE_POSITION = 435
MEASURED_ORDINAL = 64
EXACT_MAXIMUM = 257_887
PLAN_ID = "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
PREDECESSOR_PLAN_ID = (
    "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
)
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_MANIFEST_ID = "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
SUCCESSOR_PROTOCOL_SHA256 = "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
SUCCESSOR_F2_ID = "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
SOURCE_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
CONTEXT_OBJECT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV2V4_9F_RawV8"
)
RECORD_REFERENCE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8"
)
PACK_DOMAIN = "RiskYieldMMStep2Case435ContextPackV1V4_9F_RawV8"
PACK_VERSION = "riskyieldmm.raw_v8_step2_external_schema_v2.case435_context_pack.v1"
CANDIDATE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2Case435PackedContextCandidateV1V4_9F_RawV8"
)
CANDIDATE_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "constructive_candidate_envelope.case435_packed_context.v1"
)
SOURCE_ERROR_DETAIL_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"
EXPECTED_RESOURCE_VECTOR = (
    1,
    35_384,
    158,
    1_002,
    347_899,
    4,
    158,
    106_269,
    789_225,
    879_955,
    1_480_733,
    10,
    12_531,
    137,
    17,
    137,
    38_451,
    37_195,
)
EXPECTED_STREAM_SHA256 = (
    "b35d70426261fc07da100f3d0f9486ccdd03a21e1699ab2008f97d58ecc3fc83"
)
APPLICATIONS = (
    ("APPLY/SELECTOR_MARKER_CONTRACT_V1", 1),
    ("APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1", 67),
    ("APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1", 67),
    ("APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1", 1),
    ("APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1", 1),
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


def _reseal_candidate(candidate: dict[str, Any], domain: str = CANDIDATE_DOMAIN) -> None:
    payload = {
        name: value
        for name, value in candidate.items()
        if name != "constructive_candidate_id"
    }
    candidate["constructive_candidate_id"] = _semantic_id(domain, payload)


@functools.cache
def _type_descriptors() -> dict[str, dict[str, Any]]:
    return {
        row["type_name"]: row
        for row in _load(REGISTRY)["ordered_external_type_descriptors"]
    }


def _reseal_typed_record(record: dict[str, Any], type_name: str) -> None:
    descriptor = _type_descriptors()[type_name]
    identity_field = descriptor["identity_field"]
    assert identity_field is not None
    payload = {
        name: record[name]
        for name in descriptor["identity_payload_member_order"]
    }
    record[identity_field] = _seed_semantic_id(
        descriptor["described_record_domain"], payload
    )


def _reseal_source_error_detail(field: dict[str, Any]) -> None:
    error_class = field["source_error_class"]
    assert isinstance(error_class, str)
    payload = {
        "field_id": field["field_id"],
        "observation_method": field["observation_method"],
        "source_failure_phase": field["source_failure_phase"],
        "source_errno_number": field["source_errno_number"],
        "source_errno_name": field["source_errno_name"],
        "source_error_class": error_class,
    }
    field["source_error_detail_sha256"] = _seed_semantic_id(
        SOURCE_ERROR_DETAIL_DOMAIN, payload
    )


def _authority_provenance() -> tuple[str, str]:
    seed = _load(SEED)
    rows = {
        row["authority_role"]: row for row in seed["ordered_authority_binding_records"]
    }
    return (
        rows["STRUCTURAL_REGISTRY"]["semantic_id"],
        rows["RULE_LITERAL_AUTHORITY"]["raw_sha256"],
    )


def _record_reference(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "maximum_record_reference_id": _seed_semantic_id(
            RECORD_REFERENCE_DOMAIN, payload
        ),
    }


def _record_reference_for(
    record: dict[str, Any],
    *,
    kind: str,
    type_name: str,
    identity_field: str,
    context_object_id: str | None = None,
    pointer: str | None = None,
) -> dict[str, Any]:
    raw = _canonical_bytes(record)
    payload: dict[str, Any] = {"reference_kind": kind}
    if kind == "CONTEXT_OBJECT":
        assert context_object_id is not None and pointer is None
        payload["maximum_context_object_id"] = context_object_id
    elif kind == "V3_INVENTORY_POINTER":
        assert pointer is not None and context_object_id is None
        payload["source_inventory_sha256"] = SOURCE_INVENTORY_ID
        payload["inventory_json_pointer"] = pointer
    else:
        assert kind == "WITNESS_RECORD" and context_object_id is pointer is None
    payload.update(
        {
            "record_type_name": type_name,
            "record_identity_field": identity_field,
            "record_identity": record[identity_field],
            "record_canonical_byte_length": len(raw),
            "record_canonical_sha256": _sha256(raw),
        }
    )
    return _record_reference(payload)


def _context_object(
    record: dict[str, Any], type_name: str, identity_field: str
) -> dict[str, Any]:
    registry_id, literal_sha = _authority_provenance()
    raw = _canonical_bytes(record)
    payload = {
        "maximum_protocol_sha256": SUCCESSOR_PROTOCOL_SHA256,
        "source_inventory_sha256": SOURCE_INVENTORY_ID,
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "record_type_name": type_name,
        "record_identity_field": identity_field,
        "record_identity": record[identity_field],
        "record_canonical_byte_length": len(raw),
        "record_canonical_sha256": _sha256(raw),
        "record": record,
    }
    return {
        "maximum_context_object_id": _seed_semantic_id(
            CONTEXT_OBJECT_DOMAIN, payload
        ),
        **payload,
    }


def _invocations() -> list[dict[str, Any]]:
    rows = []
    for name, count in APPLICATIONS:
        if count == 1:
            rows.append(
                {
                    "application_name": name,
                    "application_invocation_ordinal": 0,
                    "bound_observation_ordinal": None,
                }
            )
        else:
            rows.extend(
                {
                    "application_name": name,
                    "application_invocation_ordinal": ordinal,
                    "bound_observation_ordinal": ordinal,
                }
                for ordinal in range(count)
            )
    assert len(rows) == 137
    return rows


def _load_c2_constructor() -> Any:
    specification = importlib.util.spec_from_file_location(
        "case435_untrusted_fixture_constructor", C2_CONSTRUCTOR
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def case435_fixture() -> dict[str, Any]:
    certificate = _load_c2_constructor().construct(ROOT)
    retained = certificate["retained_witness_context"]
    selector = retained["checkpoint_selector"]
    root = retained["target_observation_root"]
    observations = retained["ordered_observations"]
    witness = observations[MEASURED_ORDINAL]
    assert len(observations) == 67
    assert len(_canonical_bytes(witness)) == EXACT_MAXIMUM

    logical_objects = [
        _context_object(root, "TargetObservationRootV2", "target_observation_root_sha256")
    ]
    logical_objects.extend(
        _context_object(observation, "TargetObservationV2", "observation_id")
        for ordinal, observation in enumerate(observations)
        if ordinal != MEASURED_ORDINAL
    )
    logical_objects.sort(key=lambda row: row["maximum_context_object_id"])
    assert len(logical_objects) == 67
    object_by_identity = {
        row["record_identity"]: row for row in logical_objects
    }
    pack_rows = []
    for position, row in enumerate(logical_objects, 1):
        pack_rows.append(
            {
                "context_object_position": position,
                "maximum_context_object_id": row["maximum_context_object_id"],
                "record_type_name": row["record_type_name"],
                "record_identity_field": row["record_identity_field"],
                "record_identity": row["record_identity"],
                "record_canonical_byte_length": row["record_canonical_byte_length"],
                "record_canonical_sha256": row["record_canonical_sha256"],
                "record": row["record"],
            }
        )
    boundary = _load(BOUNDARY)
    pack_payload = {
        "context_pack_version": PACK_VERSION,
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "maximum_protocol_sha256": SUCCESSOR_PROTOCOL_SHA256,
        "case_position": CASE_POSITION,
        "pack_position": 1,
        "ordered_context_object_records": pack_rows,
    }
    pack = {
        **pack_payload,
        "context_pack_id": _semantic_id(PACK_DOMAIN, pack_payload),
    }
    pack_raw = _canonical_bytes(pack)
    pack_id = pack["context_pack_id"]
    pack_path = f"context_objects/packs/{pack_id[:2]}/{pack_id}.json"

    inventory = _load(INVENTORY)
    target_registry = inventory["target_field_registry"]
    marker_contract = inventory["marker_contract"]
    root_object = object_by_identity[root["target_observation_root_sha256"]]
    observation_references = []
    for ordinal, observation in enumerate(observations):
        if ordinal == MEASURED_ORDINAL:
            reference = _record_reference_for(
                observation,
                kind="WITNESS_RECORD",
                type_name="TargetObservationV2",
                identity_field="observation_id",
            )
        else:
            object_row = object_by_identity[observation["observation_id"]]
            reference = _record_reference_for(
                observation,
                kind="CONTEXT_OBJECT",
                type_name="TargetObservationV2",
                identity_field="observation_id",
                context_object_id=object_row["maximum_context_object_id"],
            )
        observation_references.append(reference)
    scope = {
        "context_kind": "ROOT_APPLICATION",
        "constraint_scope_profile_id": PROFILE_ID,
        "selected_root_family_position": 1,
        "measured_sequence_ordinal": MEASURED_ORDINAL,
        "root_record_reference": _record_reference_for(
            root,
            kind="CONTEXT_OBJECT",
            type_name="TargetObservationRootV2",
            identity_field="target_observation_root_sha256",
            context_object_id=root_object["maximum_context_object_id"],
        ),
        "selector_authority_reference": _record_reference_for(
            selector,
            kind="V3_INVENTORY_POINTER",
            type_name="CheckpointSelectorV1",
            identity_field="checkpoint_selector_id",
            pointer="/checkpoint_selector_catalog/3/selector",
        ),
        "target_field_registry_authority_reference": _record_reference_for(
            target_registry,
            kind="V3_INVENTORY_POINTER",
            type_name="TargetFieldRegistryV1",
            identity_field="target_field_registry_id",
            pointer="/target_field_registry",
        ),
        "marker_contract_authority_reference": _record_reference_for(
            marker_contract,
            kind="V3_INVENTORY_POINTER",
            type_name="MarkerContractV1",
            identity_field="marker_contract_id",
            pointer="/marker_contract",
        ),
        "ordered_observation_record_references": observation_references,
        "ordered_application_invocations": _invocations(),
    }
    seed = _load(SEED)
    seed_delta = _load(SEED_DELTA)
    case = seed["case_universe_catalog"]["ordered_case_bindings"][CASE_POSITION - 1]
    plan = seed_delta["successor_case435_logical_count_plan"]
    candidate_payload = {
        "candidate_kind": "MAXIMUM_WITNESS_PACKED_CONTEXT",
        "witness_record": witness,
        "scope_witness_context": scope,
        "ordered_context_pack_entries": [
            {
                "context_pack_position": 1,
                "context_pack_id": pack_id,
                "first_maximum_context_object_id": pack_rows[0][
                    "maximum_context_object_id"
                ],
                "last_maximum_context_object_id": pack_rows[-1][
                    "maximum_context_object_id"
                ],
                "context_object_count": len(pack_rows),
                "repository_relative_path": pack_path,
                "raw_octet_count": len(pack_raw),
                "raw_sha256": _sha256(pack_raw),
            }
        ],
    }
    candidate_payload_for_id = {
        "candidate_version": CANDIDATE_VERSION,
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": SUCCESSOR_SEED_ID,
        "finalization_manifest_id": SUCCESSOR_MANIFEST_ID,
        "case_position": CASE_POSITION,
        "case_kind": case["case_kind"],
        "case_binding": copy.deepcopy(case["case_binding"]),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": candidate_payload,
    }
    candidate = {
        **candidate_payload_for_id,
        "constructive_candidate_id": _semantic_id(
            CANDIDATE_DOMAIN, candidate_payload_for_id
        ),
    }
    return {
        "candidate": candidate,
        "candidate_raw": _pretty_bytes(candidate),
        "pack": pack,
        "pack_raw": pack_raw,
        "pack_path": pack_path,
        "certificate": certificate,
    }


def _pack_row_for(
    record: dict[str, Any], type_name: str, identity_field: str
) -> dict[str, Any]:
    logical = _context_object(record, type_name, identity_field)
    return {
        "context_object_position": 0,
        "maximum_context_object_id": logical["maximum_context_object_id"],
        "record_type_name": type_name,
        "record_identity_field": identity_field,
        "record_identity": logical["record_identity"],
        "record_canonical_byte_length": logical["record_canonical_byte_length"],
        "record_canonical_sha256": logical["record_canonical_sha256"],
        "record": record,
    }


def _refresh_bundle(
    bundle: dict[str, Any], *, sort_records: bool = True
) -> dict[str, Any]:
    pack = bundle["pack"]
    rows = pack["ordered_context_object_records"]
    if sort_records:
        rows.sort(key=lambda row: row["maximum_context_object_id"])
    for position, row in enumerate(rows, 1):
        row["context_object_position"] = position
    payload = {
        name: value for name, value in pack.items() if name != "context_pack_id"
    }
    pack["context_pack_id"] = _semantic_id(PACK_DOMAIN, payload)
    pack_raw = _canonical_bytes(pack)
    pack_id = pack["context_pack_id"]
    pack_path = f"context_objects/packs/{pack_id[:2]}/{pack_id}.json"
    entry = {
        "context_pack_position": 1,
        "context_pack_id": pack_id,
        "first_maximum_context_object_id": rows[0]["maximum_context_object_id"],
        "last_maximum_context_object_id": rows[-1]["maximum_context_object_id"],
        "context_object_count": len(rows),
        "repository_relative_path": pack_path,
        "raw_octet_count": len(pack_raw),
        "raw_sha256": _sha256(pack_raw),
    }
    bundle["candidate"]["candidate_payload"]["ordered_context_pack_entries"] = [
        entry
    ]
    _reseal_candidate(bundle["candidate"])
    bundle["candidate_raw"] = _pretty_bytes(bundle["candidate"])
    bundle["pack_raw"] = pack_raw
    bundle["pack_path"] = pack_path
    return bundle


def _clone_bundle(case435_fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": copy.deepcopy(case435_fixture["candidate"]),
        "candidate_raw": case435_fixture["candidate_raw"],
        "pack": copy.deepcopy(case435_fixture["pack"]),
        "pack_raw": case435_fixture["pack_raw"],
        "pack_path": case435_fixture["pack_path"],
    }


def _mutated_witness_bundle(
    case435_fixture: dict[str, Any],
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    bundle = _clone_bundle(case435_fixture)
    candidate = bundle["candidate"]
    witness = candidate["candidate_payload"]["witness_record"]
    old_observation_id = witness["observation_id"]
    old_context_id = witness["observation_context_id"]
    mutation(witness)
    _reseal_typed_record(witness["observation_context"], "TargetObservationContextV2")
    witness["observation_context_id"] = witness["observation_context"][
        "observation_context_id"
    ]
    for field in witness["field_observations"]:
        assert field["observation_context_id"] == old_context_id
        field["observation_context_id"] = witness["observation_context_id"]
        _reseal_typed_record(field, "TargetFieldObservationV1")
    _reseal_typed_record(witness, "TargetObservationV2")

    scope = candidate["candidate_payload"]["scope_witness_context"]
    scope["ordered_observation_record_references"][MEASURED_ORDINAL] = (
        _record_reference_for(
            witness,
            kind="WITNESS_RECORD",
            type_name="TargetObservationV2",
            identity_field="observation_id",
        )
    )
    rows = bundle["pack"]["ordered_context_object_records"]
    root_position = next(
        position
        for position, row in enumerate(rows)
        if row["record_type_name"] == "TargetObservationRootV2"
    )
    root = copy.deepcopy(rows[root_position]["record"])
    assert root["ordered_observation_ids"][MEASURED_ORDINAL] == old_observation_id
    root["ordered_observation_ids"][MEASURED_ORDINAL] = witness["observation_id"]
    _reseal_typed_record(root, "TargetObservationRootV2")
    root_row = _pack_row_for(
        root, "TargetObservationRootV2", "target_observation_root_sha256"
    )
    rows[root_position] = root_row
    scope["root_record_reference"] = _record_reference_for(
        root,
        kind="CONTEXT_OBJECT",
        type_name="TargetObservationRootV2",
        identity_field="target_observation_root_sha256",
        context_object_id=root_row["maximum_context_object_id"],
    )
    return _refresh_bundle(bundle)


def _mutated_root_bundle(
    case435_fixture: dict[str, Any],
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    bundle = _clone_bundle(case435_fixture)
    rows = bundle["pack"]["ordered_context_object_records"]
    root_position = next(
        position
        for position, row in enumerate(rows)
        if row["record_type_name"] == "TargetObservationRootV2"
    )
    root = copy.deepcopy(rows[root_position]["record"])
    mutation(root)
    _reseal_typed_record(root, "TargetObservationRootV2")
    root_row = _pack_row_for(
        root, "TargetObservationRootV2", "target_observation_root_sha256"
    )
    rows[root_position] = root_row
    scope = bundle["candidate"]["candidate_payload"]["scope_witness_context"]
    scope["root_record_reference"] = _record_reference_for(
        root,
        kind="CONTEXT_OBJECT",
        type_name="TargetObservationRootV2",
        identity_field="target_observation_root_sha256",
        context_object_id=root_row["maximum_context_object_id"],
    )
    return _refresh_bundle(bundle)


def _publish_candidate(
    root: pathlib.Path, candidate: dict[str, Any], pack_path: str, pack_raw: bytes
) -> None:
    root.mkdir(mode=0o700)
    pack_file = root / pack_path
    pack_file.parent.mkdir(parents=True, mode=0o700)
    (root / "candidate.json").write_bytes(_pretty_bytes(candidate))
    pack_file.write_bytes(pack_raw)


def _output_snapshot(root: pathlib.Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _assert_rejected(
    completed: subprocess.CompletedProcess[bytes], output_root: pathlib.Path
) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"
    )
    assert b"INTERNAL_FAIL_CLOSED" not in completed.stderr
    assert completed.stderr.count(b"\n") == 1
    assert not output_root.exists()


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


def test_case435_is_exact_deterministic_immutable_and_f2_bounded(
    tmp_path: pathlib.Path, case435_fixture: dict[str, Any]
) -> None:
    assert b"case435_attainer_certificate_id" not in case435_fixture["candidate_raw"]
    limits = _load(MANIFEST)["ordered_f2_limit_records"]
    snapshots = []
    for run_position in (1, 2):
        candidate_root = tmp_path / f"candidate-{run_position}"
        output_root = tmp_path / f"output-{run_position}"
        _publish_candidate(
            candidate_root,
            case435_fixture["candidate"],
            case435_fixture["pack_path"],
            case435_fixture["pack_raw"],
        )
        input_before = _output_snapshot(candidate_root)
        completed = _run(candidate_root, output_root)
        assert completed.returncode == 0, completed.stderr.decode()
        assert completed.stdout == completed.stderr == b""
        assert _output_snapshot(candidate_root) == input_before

        result = _load(output_root / "maximum_attainer.json")
        receipt = _load(output_root / "verification_receipt.json")
        witness = case435_fixture["candidate"]["candidate_payload"][
            "witness_record"
        ]
        assert result["canonical_byte_length"] == EXACT_MAXIMUM
        assert result["certified_analytic_maximum_octets"] == EXACT_MAXIMUM
        assert result["canonical_sha256"] == _sha256(_canonical_bytes(witness))
        assert result["witness_record"] == witness
        assert result["constraint_scope"] == "FROZEN_ROOT_APPLICATION"
        assert result["constraint_scope_profile_id"] == PROFILE_ID
        assert result["maximum_protocol_sha256"] == SUCCESSOR_PROTOCOL_SHA256
        assert result["required_context_object_count"] == 67
        assert len(result["ordered_required_context_object_ids"]) == 67
        certificate = result["upper_bound_certificate"]
        assert certificate["derivation_plan_id"] == PLAN_ID
        assert certificate["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
        assert certificate["ordered_safe_relaxation_rule_ids"] == []
        assert certificate["certified_upper_bound_octets"] == EXACT_MAXIMUM
        assert certificate["streamed_derivation_result_sha256"] == (
            EXPECTED_STREAM_SHA256
        )
        report = result["proof_resource_report"]
        vector = tuple(
            row["measured_value"]
            for row in report["ordered_resource_measurements"]
        )
        assert report["resource_limit_catalog_id"] == SUCCESSOR_F2_ID
        assert vector == EXPECTED_RESOURCE_VECTOR
        assert all(
            measured <= limit["f2_per_case"]
            for measured, limit in zip(vector, limits, strict=True)
        )
        assert receipt["seed_catalog_id"] == SUCCESSOR_SEED_ID
        assert receipt["finalization_manifest_id"] == SUCCESSOR_MANIFEST_ID
        assert receipt["logical_count_plan_id"] == PLAN_ID
        assert receipt["verification_status"] == "P1_P2_P3_ACCEPTED"
        assert len(receipt["ordered_verified_context_object_entries"]) == 67
        assert len(list((output_root / "context_objects").glob("*/*.json"))) == 67
        snapshots.append(_output_snapshot(output_root))
    assert snapshots[0] == snapshots[1]


def test_case435_requires_the_packed_transport_boundary(
    tmp_path: pathlib.Path, case435_fixture: dict[str, Any]
) -> None:
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        case435_fixture["candidate"],
        case435_fixture["pack_path"],
        case435_fixture["pack_raw"],
    )
    _assert_rejected(
        _run(candidate_root, output_root, boundary=SUCCESSOR_BOUNDARY),
        output_root,
    )


def _old_plan(candidate: dict[str, Any]) -> None:
    candidate["logical_count_plan_id"] = PREDECESSOR_PLAN_ID


def _producer_certificate_claim(candidate: dict[str, Any]) -> None:
    candidate["candidate_payload"]["case435_attainer_certificate_id"] = "0" * 64


@pytest.mark.parametrize(
    "mutation",
    [_old_plan, _producer_certificate_claim],
    ids=["shadowed-predecessor-plan", "producer-certificate-claim"],
)
def test_case435_rejects_resealed_authority_or_c2_trust_substitutions(
    tmp_path: pathlib.Path,
    case435_fixture: dict[str, Any],
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    bundle = _clone_bundle(case435_fixture)
    mutation(bundle["candidate"])
    _reseal_candidate(bundle["candidate"])
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_case435_rejects_the_inherited_flat_candidate_encoding(
    tmp_path: pathlib.Path, case435_fixture: dict[str, Any]
) -> None:
    bundle = _clone_bundle(case435_fixture)
    boundary = _load(BOUNDARY)
    inherited = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    bundle["candidate"]["candidate_version"] = inherited["version_literal"]
    _reseal_candidate(bundle["candidate"], inherited["identity_domain"])
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    _assert_rejected(_run(candidate_root, output_root), output_root)


def _wrong_measured_ordinal(scope: dict[str, Any]) -> None:
    scope["measured_sequence_ordinal"] = MEASURED_ORDINAL - 1


def _wrong_schedule(scope: dict[str, Any]) -> None:
    scope["ordered_application_invocations"][0]["application_name"] = (
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1"
    )


def _swapped_observation_references(scope: dict[str, Any]) -> None:
    references = scope["ordered_observation_record_references"]
    references[0], references[1] = references[1], references[0]


def _wrong_selector_pointer(scope: dict[str, Any]) -> None:
    selector = _load(INVENTORY)["checkpoint_selector_catalog"][2]["selector"]
    scope["selector_authority_reference"] = _record_reference_for(
        selector,
        kind="V3_INVENTORY_POINTER",
        type_name="CheckpointSelectorV1",
        identity_field="checkpoint_selector_id",
        pointer="/checkpoint_selector_catalog/2/selector",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        _wrong_measured_ordinal,
        _wrong_schedule,
        _swapped_observation_references,
        _wrong_selector_pointer,
    ],
    ids=[
        "measured-ordinal",
        "application-schedule",
        "observation-reference-order",
        "fixed-selector-pointer",
    ],
)
def test_case435_rejects_resealed_context_or_schedule_substitutions(
    tmp_path: pathlib.Path,
    case435_fixture: dict[str, Any],
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    bundle = _clone_bundle(case435_fixture)
    scope = bundle["candidate"]["candidate_payload"]["scope_witness_context"]
    mutation(scope)
    _reseal_candidate(bundle["candidate"])
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    _assert_rejected(_run(candidate_root, output_root), output_root)


def _remove_context_object(bundle: dict[str, Any]) -> None:
    bundle["pack"]["ordered_context_object_records"].pop()


def _duplicate_context_object(bundle: dict[str, Any]) -> None:
    rows = bundle["pack"]["ordered_context_object_records"]
    rows[-1] = copy.deepcopy(rows[-2])


def _duplicate_inline_witness_in_pack(bundle: dict[str, Any]) -> None:
    witness = bundle["candidate"]["candidate_payload"]["witness_record"]
    bundle["pack"]["ordered_context_object_records"].append(
        _pack_row_for(witness, "TargetObservationV2", "observation_id")
    )


@pytest.mark.parametrize(
    "mutation",
    [_remove_context_object, _duplicate_context_object, _duplicate_inline_witness_in_pack],
    ids=["missing-object", "duplicate-object", "inline-witness-duplicated"],
)
def test_case435_rejects_resealed_incomplete_or_duplicate_pack_closures(
    tmp_path: pathlib.Path,
    case435_fixture: dict[str, Any],
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    bundle = _clone_bundle(case435_fixture)
    mutation(bundle)
    _refresh_bundle(bundle)
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_case435_rejects_a_resealed_noncanonical_pack_order(
    tmp_path: pathlib.Path, case435_fixture: dict[str, Any]
) -> None:
    bundle = _clone_bundle(case435_fixture)
    rows = bundle["pack"]["ordered_context_object_records"]
    rows[0], rows[1] = rows[1], rows[0]
    _refresh_bundle(bundle, sort_records=False)
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    _assert_rejected(_run(candidate_root, output_root), output_root)


def _descriptor_policy_false(witness: dict[str, Any]) -> None:
    field = witness["field_observations"][20]
    assert field["unavailable_reason"] == "SOURCE_CLOCK_UNAVAILABLE"
    assert len(field["source_error_class"]) == 256
    field["unavailable_reason"] = "NO_FROZEN_PRESSURE_POLICY"
    field["source_error_class"] = field["source_error_class"][:-1]
    _reseal_source_error_detail(field)


def _nonattaining_witness(witness: dict[str, Any]) -> None:
    field = witness["field_observations"][0]
    assert len(field["source_error_class"]) == 256
    field["source_error_class"] = field["source_error_class"][:-1]
    _reseal_source_error_detail(field)


def _aggregate_registry_false(witness: dict[str, Any]) -> None:
    witness["observation_context"]["target_field_registry_id"] = "0" * 64


def _root_membership_false(root: dict[str, Any]) -> None:
    root["ordered_observation_ids"][0] = "0" * 64


def _root_lifecycle_false(root: dict[str, Any]) -> None:
    root["full_checkpoint_selector_id"] = "0" * 64


def _codec_oversize(witness: dict[str, Any]) -> None:
    field = witness["field_observations"][0]
    assert len(field["source_error_class"]) == 256
    field["source_error_class"] += "z"
    _reseal_source_error_detail(field)


@pytest.mark.parametrize(
    ("mutation", "expected_octets"),
    [
        (_descriptor_policy_false, EXACT_MAXIMUM),
        (_nonattaining_witness, EXACT_MAXIMUM - 1),
    ],
    ids=["p1-descriptor-policy-false", "p3-nonattainment"],
)
def test_case435_rejects_resealed_p1_or_p3_failures(
    tmp_path: pathlib.Path,
    case435_fixture: dict[str, Any],
    mutation: Callable[[dict[str, Any]], None],
    expected_octets: int,
) -> None:
    bundle = _mutated_witness_bundle(case435_fixture, mutation)
    witness = bundle["candidate"]["candidate_payload"]["witness_record"]
    assert len(_canonical_bytes(witness)) == expected_octets
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    _assert_rejected(_run(candidate_root, output_root), output_root)


@pytest.mark.parametrize(
    "failure_kind",
    ["field-context", "membership", "lifecycle", "codec"],
)
def test_case435_rejects_distinct_resealed_semantic_guard_failures(
    tmp_path: pathlib.Path,
    case435_fixture: dict[str, Any],
    failure_kind: str,
) -> None:
    if failure_kind == "field-context":
        bundle = _mutated_witness_bundle(
            case435_fixture, _aggregate_registry_false
        )
        expected = b"RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1"
    elif failure_kind == "membership":
        bundle = _mutated_root_bundle(case435_fixture, _root_membership_false)
        expected = b"case435 retained record/reference closure differs"
    elif failure_kind == "lifecycle":
        bundle = _mutated_root_bundle(case435_fixture, _root_lifecycle_false)
        expected = b"case435 retained record/reference closure differs"
    else:
        assert failure_kind == "codec"
        bundle = _mutated_witness_bundle(case435_fixture, _codec_oversize)
        expected = b"WITNESS_ILLEGAL"
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        bundle["candidate"],
        bundle["pack_path"],
        bundle["pack_raw"],
    )
    completed = _run(candidate_root, output_root)
    _assert_rejected(completed, output_root)
    assert expected in completed.stderr


def test_case435_keeps_candidate_pack_file_closure_exact(
    tmp_path: pathlib.Path, case435_fixture: dict[str, Any]
) -> None:
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root,
        case435_fixture["candidate"],
        case435_fixture["pack_path"],
        case435_fixture["pack_raw"],
    )
    (candidate_root / "context_objects" / "unreferenced.json").write_bytes(b"{}")
    _assert_rejected(_run(candidate_root, output_root), output_root)


def test_v3_source_is_static_and_isolated_from_producers_and_proof_checkers() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    dynamic_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert dynamic_calls.isdisjoint({"__import__", "compile", "eval", "exec"})
    assert "importlib" not in imported_roots
    assert "class _Case435RuleRuntime:" in source
    for forbidden in (
        "construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py",
        "check_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py",
        "check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py",
        "check_raw_v8_step2_maximum_protocol_v2_case435_exactness_join_v49f.py",
    ):
        assert forbidden not in source
