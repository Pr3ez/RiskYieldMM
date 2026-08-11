"""Independent A4-P6-V0 authority-resolution and read-barrier acceptance."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_RELATIVE = Path(
    "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER = ROOT / VERIFIER_RELATIVE
PREDECESSOR_BOUNDARY_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SUCCESSOR_BOUNDARY_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
SEED_RELATIVE = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
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

SUCCESSOR_SEED_ID = (
    "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
)
SUCCESSOR_MANIFEST_ID = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
SUCCESSOR_MANIFEST_SHA256 = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
SUCCESSOR_F2_ID = (
    "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
)


def _load(relative: Path) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_bytes())


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


def _semantic_id(domain: str, payload: Any) -> str:
    return hashlib.sha256(
        _canonical_bytes({"domain": domain, "payload": payload})
    ).hexdigest()


def _candidate(*, successor: bool) -> dict[str, Any]:
    boundary = _load(PREDECESSOR_BOUNDARY_RELATIVE)
    seed = _load(SEED_RELATIVE)
    manifest = _load(MANIFEST_RELATIVE)
    case = seed["case_universe_catalog"]["ordered_case_bindings"][4]
    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        4
    ]
    value = {
        "candidate_version": boundary["candidate_bundle_contract"][
            "candidate_envelope_schema"
        ]["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": (
            SUCCESSOR_SEED_ID if successor else seed["seed_catalog_id"]
        ),
        "finalization_manifest_id": (
            SUCCESSOR_MANIFEST_ID
            if successor
            else manifest["finalization_manifest_id"]
        ),
        "case_position": 5,
        "case_kind": case["case_kind"],
        "case_binding": copy.deepcopy(case["case_binding"]),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": {"kind": "BOOL", "value": False},
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        },
    }
    domain = boundary["candidate_bundle_contract"]["candidate_envelope_schema"][
        "identity_domain"
    ]
    value["constructive_candidate_id"] = _semantic_id(domain, value)
    return value


def _publish_candidate(root: Path, candidate: dict[str, Any]) -> bytes:
    root.mkdir(mode=0o700)
    (root / "context_objects").mkdir(mode=0o700)
    raw = _pretty_bytes(candidate)
    (root / "candidate.json").write_bytes(raw)
    return raw


def _run(
    repository_root: Path,
    verifier: Path,
    boundary: Path,
    candidate_root: Path,
    output_root: Path,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(verifier),
            "--repository-root",
            str(repository_root),
            "--boundary",
            str(boundary),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=repository_root,
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
    completed: subprocess.CompletedProcess[bytes], output_root: Path, code: bytes
) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_" + code + b":"
    )
    assert completed.stderr.count(b"\n") == 1
    assert not output_root.exists()


def _assert_identity(value: dict[str, Any], id_name: str, domain: str) -> None:
    payload = {name: child for name, child in value.items() if name != id_name}
    assert value[id_name] == _semantic_id(domain, payload)


def _copy_minimal_authority_repository(destination: Path) -> None:
    boundary = _load(PREDECESSOR_BOUNDARY_RELATIVE)
    seed = _load(SEED_RELATIVE)
    seed_delta = _load(SEED_DELTA_RELATIVE)
    relatives = {
        VERIFIER_RELATIVE,
        PREDECESSOR_BOUNDARY_RELATIVE,
        SUCCESSOR_BOUNDARY_RELATIVE,
        SEED_RELATIVE,
        MANIFEST_RELATIVE,
        SEED_DELTA_RELATIVE,
        MANIFEST_DELTA_RELATIVE,
        TARGET_DELTA_RELATIVE,
        PREDECESSOR_TARGET_RELATIVE,
        TYPED_RUNTIME_RELATIVE,
    }
    for row in seed["ordered_authority_binding_records"]:
        relatives.add(Path(row["repository_relative_path"]))
    legacy = boundary["legacy_v1_exclusion_contract"]
    for name in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        relatives.add(Path(legacy[name]["repository_relative_path"]))
    for row in seed_delta["exactness_theorem_authority"][
        "ordered_source_authority_records"
    ]:
        relatives.add(Path(row["repository_relative_path"]))
    for relative in sorted(relatives):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def test_v0_source_is_one_stdlib_only_verifier_without_producer_or_checker_imports() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported == {
        "hashlib",
        "json",
        "os",
        "pathlib",
        "stat",
        "sys",
        "tempfile",
    }
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "subprocess" not in source
    assert "importlib" not in source
    assert "runpy" not in source


def test_v0_preserves_predecessor_case5_and_accepts_successor_case5(
    tmp_path: Path,
) -> None:
    cases = (
        (False, ROOT / PREDECESSOR_BOUNDARY_RELATIVE, "predecessor"),
        (True, ROOT / SUCCESSOR_BOUNDARY_RELATIVE, "successor"),
    )
    for successor, boundary, name in cases:
        candidate_root = tmp_path / f"candidate-{name}"
        output_root = tmp_path / f"output-{name}"
        candidate_raw = _publish_candidate(
            candidate_root, _candidate(successor=successor)
        )
        completed = _run(ROOT, VERIFIER, boundary, candidate_root, output_root)
        assert completed.returncode == 0, completed.stderr.decode()
        assert completed.stdout == completed.stderr == b""
        result = json.loads((output_root / "maximum_attainer.json").read_bytes())
        receipt = json.loads(
            (output_root / "verification_receipt.json").read_bytes()
        )
        output_contract = _load(PREDECESSOR_BOUNDARY_RELATIVE)[
            "verifier_output_contract"
        ]
        _assert_identity(
            result,
            "maximum_attainer_id",
            output_contract["maximum_attainer_schema"]["identity_domain"],
        )
        _assert_identity(
            result["upper_bound_certificate"],
            "upper_bound_certificate_id",
            output_contract["upper_bound_certificate_schema"]["identity_domain"],
        )
        _assert_identity(
            result["proof_resource_report"],
            "proof_resource_report_id",
            output_contract["proof_resource_report_schema"]["identity_domain"],
        )
        _assert_identity(
            receipt,
            "verification_receipt_id",
            output_contract["verification_receipt_schema"]["identity_domain"],
        )
        assert (candidate_root / "candidate.json").read_bytes() == candidate_raw
        assert result["canonical_byte_length"] == 29
        assert result["witness_record"] == {"kind": "BOOL", "value": False}
        if successor:
            assert receipt["seed_catalog_id"] == SUCCESSOR_SEED_ID
            assert receipt["finalization_manifest_id"] == SUCCESSOR_MANIFEST_ID
            assert result["maximum_protocol_sha256"] == SUCCESSOR_MANIFEST_SHA256
            assert (
                result["upper_bound_certificate"]["maximum_protocol_sha256"]
                == SUCCESSOR_MANIFEST_SHA256
            )
            assert (
                result["proof_resource_report"]["maximum_protocol_sha256"]
                == SUCCESSOR_MANIFEST_SHA256
            )
            assert (
                result["proof_resource_report"]["resource_limit_catalog_id"]
                == SUCCESSOR_F2_ID
            )


def test_v0_successor_mode_is_byte_deterministic(tmp_path: Path) -> None:
    outputs: list[tuple[bytes, bytes]] = []
    for ordinal in (1, 2):
        candidate_root = tmp_path / f"candidate-{ordinal}"
        output_root = tmp_path / f"output-{ordinal}"
        _publish_candidate(candidate_root, _candidate(successor=True))
        completed = _run(
            ROOT,
            VERIFIER,
            ROOT / SUCCESSOR_BOUNDARY_RELATIVE,
            candidate_root,
            output_root,
        )
        assert completed.returncode == 0, completed.stderr.decode()
        outputs.append(
            (
                (output_root / "maximum_attainer.json").read_bytes(),
                (output_root / "verification_receipt.json").read_bytes(),
            )
        )
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    ("successor_candidate", "boundary_relative"),
    [
        (False, SUCCESSOR_BOUNDARY_RELATIVE),
        (True, PREDECESSOR_BOUNDARY_RELATIVE),
    ],
    ids=["old-candidate-under-successor", "successor-candidate-under-old"],
)
def test_v0_rejects_cross_mode_candidate_authority_ids(
    tmp_path: Path, successor_candidate: bool, boundary_relative: Path
) -> None:
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(
        candidate_root, _candidate(successor=successor_candidate)
    )
    completed = _run(
        ROOT,
        VERIFIER,
        ROOT / boundary_relative,
        candidate_root,
        output_root,
    )
    _assert_rejected(completed, output_root, b"AUTHORITY_INVALID")


def test_v0_rejects_unfrozen_boundary_selector(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    output_root = tmp_path / "output"
    _publish_candidate(candidate_root, _candidate(successor=False))
    completed = _run(
        ROOT,
        VERIFIER,
        ROOT / MANIFEST_DELTA_RELATIVE,
        candidate_root,
        output_root,
    )
    _assert_rejected(completed, output_root, b"INVOCATION_INVALID")


def test_v0_rejects_tampered_successor_authority_before_candidate_open(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "minimal-repository"
    repository.mkdir()
    _copy_minimal_authority_repository(repository)
    seed_delta_path = repository / SEED_DELTA_RELATIVE
    raw = seed_delta_path.read_bytes()
    seed_delta_path.write_bytes(raw.replace(b"case435", b"case436", 1))
    missing_candidate = repository / "candidate-must-not-be-opened"
    output_root = repository / "output"
    completed = _run(
        repository,
        repository / VERIFIER_RELATIVE,
        repository / SUCCESSOR_BOUNDARY_RELATIVE,
        missing_candidate,
        output_root,
    )
    _assert_rejected(completed, output_root, b"AUTHORITY_INVALID")
    assert b"candidate root anchor is absent" not in completed.stderr
