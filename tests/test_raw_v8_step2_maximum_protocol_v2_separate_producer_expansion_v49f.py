"""Fail-first successor target for S1-A4/A4-P6-P.

The accepted predecessor target intentionally remains red under its original
authority.  This module selects the accepted packed successor boundary and
freezes the observable producer/verifier transition without importing either
implementation.
"""

from __future__ import annotations

import ast
import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = (
    ROOT / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
PREDECESSOR_BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SUCCESSOR_BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
PACKED_BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_delta_v49f.json"
)
RUNNER = ROOT / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"

PILOT_CASES = (5, 24, 54, 69, 435, 475)
NONLEGACY_CASES = PILOT_CASES[1:]

PREDECESSOR_BOUNDARY_OCTETS = 27_334
PREDECESSOR_BOUNDARY_SHA256 = (
    "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
)
SUCCESSOR_BOUNDARY_OCTETS = 4_806
SUCCESSOR_BOUNDARY_SHA256 = (
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c"
)
PACKED_BOUNDARY_OCTETS = 6_049
PACKED_BOUNDARY_SHA256 = (
    "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b"
)
PACKED_BOUNDARY_ID = "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd"
PACKED_BOUNDARY_DOMAIN = "RiskYieldMMStep2Case435ContextPackBoundaryDeltaV1V4_9F_RawV8"
SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_MANIFEST_ID = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
EXPECTED_SUCCESSOR_PROTOCOL_SHA256 = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
CASE435_PLAN_ID = "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"

PRODUCER_MARKER = "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1"
VERIFIER_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"
RUNNER_MARKER = "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1"
PRODUCER_ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_"
VERIFIER_ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"

LEGACY_CASE5_OCTETS = 1_333
LEGACY_CASE5_SHA256 = "6dfba23c6d18e96eaf826de408f66d4c69980acbd604d3d7c66f29661f74f9f1"
LEGACY_CASE5_ID = "048df6d26b0d60f217864c32a1b420a34b8427a513a120185de43d822e73b120"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate member: {name}")
        result[name] = value
    return result


def _load(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_duplicate_guard,
        parse_float=lambda value: (_ for _ in ()).throw(ValueError(value)),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    assert type(value) is dict
    return value


def _environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_producer(
    case_position: int,
    output_root: Path,
    *,
    boundary: Path = PACKED_BOUNDARY,
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
            str(boundary),
            "--case-position",
            str(case_position),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=900,
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
            str(PACKED_BOUNDARY),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=1_800,
    )


def _assert_success(
    completed: subprocess.CompletedProcess[bytes], failure_code: str
) -> None:
    assert completed.returncode == 0, (
        f"{failure_code}: " + completed.stderr.decode("utf-8", errors="replace").strip()
    )
    assert completed.stdout == completed.stderr == b""


def _assert_producer_reject(
    completed: subprocess.CompletedProcess[bytes], output_root: Path
) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(PRODUCER_ERROR_PREFIX)
    assert completed.stderr.count(b"\n") == 1
    assert not output_root.exists()


def _snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    rows: list[tuple[str, int, int, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        assert not stat.S_ISLNK(metadata.st_mode)
        if path.is_file():
            raw = path.read_bytes()
            rows.append((relative, metadata.st_mode, len(raw), _sha256(raw)))
        else:
            rows.append((relative + "/", metadata.st_mode, 0, ""))
    return tuple(rows)


def _contains_member(value: Any, member: str) -> bool:
    if type(value) is dict:
        return member in value or any(
            _contains_member(child, member) for child in value.values()
        )
    if type(value) is list:
        return any(_contains_member(child, member) for child in value)
    return False


def _pipeline_once(base: Path, case_position: int) -> tuple[Any, ...]:
    base.mkdir(mode=0o700)
    candidate = base / "candidate"
    produced = _run_producer(case_position, candidate)
    _assert_success(produced, f"A4_P6_P_CASE_{case_position}_PRODUCER_NOT_QUALIFIED")
    assert {path.name for path in candidate.iterdir()} == {
        "candidate.json",
        "context_objects",
    }
    candidate_value = _load((candidate / "candidate.json").read_bytes())
    assert candidate_value["case_position"] == case_position
    assert candidate_value["seed_catalog_id"] == SUCCESSOR_SEED_ID
    assert candidate_value["finalization_manifest_id"] == SUCCESSOR_MANIFEST_ID
    predecessor = _load(PREDECESSOR_BOUNDARY.read_bytes())
    for forbidden in predecessor["candidate_bundle_contract"][
        "forbidden_producer_claim_member_names"
    ]:
        assert not _contains_member(candidate_value, forbidden)
    if case_position == 435:
        assert candidate_value["logical_count_plan_id"] == CASE435_PLAN_ID
        assert (
            candidate_value["candidate_payload"]["candidate_kind"]
            == "MAXIMUM_WITNESS_PACKED_CONTEXT"
        )
    before = _snapshot(candidate)
    verified = base / "verified"
    checked = _run_verifier(candidate, verified)
    _assert_success(checked, f"A4_P6_P_CASE_{case_position}_VERIFIER_NOT_QUALIFIED")
    assert _snapshot(candidate) == before
    return before, _snapshot(verified)


def test_successor_authority_is_exact_and_keeps_limits_immutable() -> None:
    for path, octets, digest in (
        (
            PREDECESSOR_BOUNDARY,
            PREDECESSOR_BOUNDARY_OCTETS,
            PREDECESSOR_BOUNDARY_SHA256,
        ),
        (SUCCESSOR_BOUNDARY, SUCCESSOR_BOUNDARY_OCTETS, SUCCESSOR_BOUNDARY_SHA256),
        (PACKED_BOUNDARY, PACKED_BOUNDARY_OCTETS, PACKED_BOUNDARY_SHA256),
    ):
        raw = path.read_bytes()
        assert len(raw) == octets
        assert _sha256(raw) == digest
    packed = _load(PACKED_BOUNDARY.read_bytes())
    payload = {
        name: value
        for name, value in packed.items()
        if name != "case435_context_pack_boundary_delta_id"
    }
    assert (
        packed["case435_context_pack_boundary_delta_id"]
        == _semantic_id(PACKED_BOUNDARY_DOMAIN, payload)
        == PACKED_BOUNDARY_ID
    )
    effective = packed["unchanged_effective_authorities"]
    assert effective["successor_seed_catalog_id"] == SUCCESSOR_SEED_ID
    assert effective["successor_manifest_id"] == SUCCESSOR_MANIFEST_ID
    assert effective["maximum_protocol_sha256"] == EXPECTED_SUCCESSOR_PROTOCOL_SHA256
    assert packed["scope_and_non_drift_contract"]["f0_or_f2_limit_increase_forbidden"]


def test_producer_role_source_remains_static_separate_and_non_authoritative() -> None:
    source = PRODUCER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
    boundary = _load(PREDECESSOR_BOUNDARY.read_bytes())
    allowed = set(
        boundary["independence_contract"]["allowed_standard_library_import_roots"]
    )
    forbidden = set(boundary["independence_contract"]["forbidden_import_roots"])
    assert imports <= allowed | {"__future__"}
    assert imports.isdisjoint(forbidden)
    assert calls.isdisjoint(
        {"__import__", "compile", "eval", "exec", "system", "popen", "fork", "execve"}
    )
    assert PRODUCER_MARKER in strings
    assert VERIFIER_MARKER not in source
    assert RUNNER_MARKER not in source
    for forbidden_path in (
        VERIFIER.relative_to(ROOT).as_posix(),
        "construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py",
        "check_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py",
        "join_raw_v8_step2_maximum_protocol_v2_case435_exactness_v49f.py",
    ):
        assert forbidden_path not in source
    assert "CANDIDATE_CONTAINS_PROOF_FIELD" in strings


def test_predecessor_case5_bytes_remain_exact(tmp_path: Path) -> None:
    output = tmp_path / "legacy-case5"
    completed = _run_producer(5, output, boundary=PREDECESSOR_BOUNDARY)
    _assert_success(completed, "A4_P6_P_PREDECESSOR_CASE5_REGRESSION")
    raw = (output / "candidate.json").read_bytes()
    candidate = _load(raw)
    assert len(raw) == LEGACY_CASE5_OCTETS
    assert _sha256(raw) == LEGACY_CASE5_SHA256
    assert candidate["constructive_candidate_id"] == LEGACY_CASE5_ID


@pytest.mark.parametrize("case_position", NONLEGACY_CASES)
def test_predecessor_mode_stays_case5_only(tmp_path: Path, case_position: int) -> None:
    output = tmp_path / f"predecessor-{case_position}"
    completed = _run_producer(
        case_position,
        output,
        boundary=PREDECESSOR_BOUNDARY,
    )
    _assert_producer_reject(completed, output)


def test_intermediate_successor_boundary_is_not_a_production_mode(
    tmp_path: Path,
) -> None:
    output = tmp_path / "intermediate"
    completed = _run_producer(24, output, boundary=SUCCESSOR_BOUNDARY)
    _assert_producer_reject(completed, output)


@pytest.mark.parametrize("case_position", PILOT_CASES)
def test_packed_successor_pipeline_is_deterministic_and_independently_verified(
    tmp_path: Path, case_position: int
) -> None:
    first = _pipeline_once(tmp_path / "first", case_position)
    second = _pipeline_once(tmp_path / "second", case_position)
    assert first == second


def test_parent_runner_remains_absent() -> None:
    assert not RUNNER.exists(), "A4_P6_P_PARENT_RUNNER_MUST_REMAIN_HELD"


def test_no_repository_private_producer_leftovers() -> None:
    assert not [
        path for path in ROOT.rglob("*") if path.name.startswith(".raw-v8-v2-producer-")
    ]
