"""Independent qualification target for the A4-P6-R parent pilot runner."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
PRODUCER = (
    ROOT / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
PACKED_BOUNDARY = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
TARGET = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
MANIFEST = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
PRODUCER_REPORT = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_acceptance_report_v49f.json"
)

RUNNER_MARKER = "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1"
PRODUCER_MARKER = "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1"
VERIFIER_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"
ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PILOT_RUNNER_"
PILOT_CASES = (5, 24, 54, 69, 435, 475)

EXPECTED_ARTIFACTS = {
    BOUNDARY: (
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
    ),
    PACKED_BOUNDARY: (
        6_049,
        "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    ),
    TARGET: (
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
    ),
    PRODUCER: (
        129_026,
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da",
    ),
    VERIFIER: (
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    PRODUCER_REPORT: (
        12_583,
        "2ef2a621df51f5193108a61ed5b639ab48378b9e5fd87daf4cfbd619a9fb20c8",
    ),
}


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


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate member: {name}")
        result[name] = value
    return result


def _reject_number(value: str) -> Any:
    raise ValueError(f"forbidden number: {value}")


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_duplicate_guard,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    assert type(value) is dict
    return value


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run(mode: str, output_root: Path) -> subprocess.CompletedProcess[bytes]:
    assert mode in {"write", "check"}
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
            str(PACKED_BOUNDARY),
            f"--{mode}-output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=3_600,
    )


def _assert_success(completed: subprocess.CompletedProcess[bytes]) -> None:
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout == completed.stderr == b""


def _assert_reject(completed: subprocess.CompletedProcess[bytes]) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(ERROR_PREFIX)
    assert completed.stderr.count(b"\n") == 1


def _file_closure(root: Path) -> tuple[int, str]:
    rows: list[dict[str, Any]] = []
    total = 0
    identities: set[tuple[int, int]] = set()
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        assert not stat.S_ISLNK(metadata.st_mode)
        if path.is_dir():
            assert stat.S_IMODE(metadata.st_mode) == 0o700
            continue
        assert path.is_file()
        assert metadata.st_nlink == 1
        identity = (metadata.st_dev, metadata.st_ino)
        assert identity not in identities
        identities.add(identity)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        raw = path.read_bytes()
        total += len(raw)
        rows.append(
            {
                "repository_relative_path": path.relative_to(root).as_posix(),
                "raw_octets": len(raw),
                "raw_sha256": _sha256(raw),
            }
        )
    return total, _sha256(_canonical_bytes(rows))


def _snapshot(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    rows = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            rows.append((relative + "/", stat.S_IMODE(metadata.st_mode), 0, ""))
        else:
            raw = path.read_bytes()
            rows.append(
                (relative, stat.S_IMODE(metadata.st_mode), len(raw), _sha256(raw))
            )
    return tuple(rows)


def _validate_output(root: Path) -> bytes:
    boundary = _load(BOUNDARY)
    packed = _load(PACKED_BOUNDARY)
    target = _load(TARGET)
    report = _load(PRODUCER_REPORT)
    schema = boundary["pilot_contract"]["pilot_manifest_schema"]
    raw = (root / "constructive_pilot_manifest.json").read_bytes()
    manifest = json.loads(raw)
    assert raw == _pretty_bytes(manifest)
    assert set(manifest) == set(schema["ordered_member_names"])
    effective = packed["unchanged_effective_authorities"]
    assert manifest["pilot_version"] == boundary["pilot_contract"]["pilot_version"]
    assert manifest["canonicalization_version"] == boundary["canonicalization_version"]
    assert manifest["protocol_version"] == boundary["protocol_version"]
    assert manifest["seed_catalog_id"] == effective["successor_seed_catalog_id"]
    assert manifest["finalization_manifest_id"] == effective["successor_manifest_id"]
    assert manifest["pilot_status"] == boundary["pilot_contract"]["pilot_status"]

    roles = {
        row["role_name"]: row
        for row in boundary["implementation_role_contract"]["ordered_role_records"]
    }
    for member, role, source in (
        ("producer_authority", "SEPARATE_PRODUCER", PRODUCER),
        ("verifier_authority", "INDEPENDENT_VERIFIER", VERIFIER),
        ("runner_authority", "PARENT_PILOT_RUNNER", RUNNER),
    ):
        source_raw = source.read_bytes()
        assert manifest[member] == {
            "repository_relative_path": roles[role]["repository_relative_path"],
            "raw_octets": len(source_raw),
            "raw_sha256": _sha256(source_raw),
            "source_marker": roles[role]["source_marker"],
        }

    expected_rows = target["ordered_pilot_case_records"]
    ledgers = {
        row["case_position"]: row for row in report["ordered_case_acceptance_records"]
    }
    aggregate = [0] * 18
    f2_rows = _load(MANIFEST)["ordered_f2_limit_records"]
    assert [row["case_position"] for row in expected_rows] == list(PILOT_CASES)
    assert {path.name for path in (root / "cases").iterdir()} == {
        f"{row['pilot_position']:04d}-{row['case_position']:04d}"
        for row in expected_rows
    }
    for expected, entry in zip(
        expected_rows, manifest["ordered_case_result_entries"], strict=True
    ):
        assert set(entry) == set(schema["case_result_entry_ordered_member_names"])
        for name in (
            "pilot_position",
            "case_position",
            "case_kind",
            "logical_count_plan_id",
        ):
            assert entry[name] == expected[name]
        case_root = (
            root
            / "cases"
            / f"{expected['pilot_position']:04d}-{expected['case_position']:04d}"
        )
        assert {path.name for path in case_root.iterdir()} == {"candidate", "verified"}
        candidate_root = case_root / "candidate"
        verified_root = case_root / "verified"
        candidate = _load(candidate_root / "candidate.json")
        receipt = _load(verified_root / "verification_receipt.json")
        result_name = (
            "local_shutdown_unrepresentable.json"
            if expected["case_position"] == 475
            else "maximum_attainer.json"
        )
        result = _load(verified_root / result_name)
        result_id = result.get("maximum_attainer_id") or result.get(
            "local_shutdown_unrepresentable_id"
        )
        candidate_octets, candidate_hash = _file_closure(candidate_root)
        verified_octets, verified_hash = _file_closure(verified_root)
        ledger = ledgers[expected["case_position"]]
        assert (
            candidate["constructive_candidate_id"]
            == ledger["constructive_candidate_id"]
        )
        assert receipt["verification_receipt_id"] == ledger["verification_receipt_id"]
        assert result_id == ledger["result_artifact_id"]
        assert entry == {
            "pilot_position": expected["pilot_position"],
            "case_position": expected["case_position"],
            "case_kind": expected["case_kind"],
            "logical_count_plan_id": expected["logical_count_plan_id"],
            "constructive_candidate_id": candidate["constructive_candidate_id"],
            "candidate_root_raw_octets": candidate_octets,
            "candidate_root_sha256": candidate_hash,
            "verification_receipt_id": receipt["verification_receipt_id"],
            "verified_result_artifact_id": result_id,
            "verified_result_root_raw_octets": verified_octets,
            "verified_result_root_sha256": verified_hash,
        }
        vector = [
            row["measured_value"]
            for row in result["proof_resource_report"]["ordered_resource_measurements"]
        ]
        assert vector == ledger["resource_vector"]
        for index, (measurement, limit) in enumerate(zip(vector, f2_rows, strict=True)):
            assert measurement <= limit["f2_per_case"]
            if limit["full_run_aggregation"] == "SUM":
                aggregate[index] += measurement
            else:
                aggregate[index] = max(aggregate[index], measurement)
    assert all(
        measured <= limit["f2_full_run"]
        for measured, limit in zip(aggregate, f2_rows, strict=True)
    )
    payload = {name: manifest[name] for name in schema["ordered_member_names"][:-1]}
    assert manifest["constructive_pilot_manifest_id"] == _semantic_id(
        schema["identity_domain"], payload
    )
    return raw


def _load_runner() -> ModuleType:
    specification = importlib.util.spec_from_file_location("a4_p6_runner", RUNNER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_frozen_authorities_and_historical_ledger_are_exact() -> None:
    for path, (octets, digest) in EXPECTED_ARTIFACTS.items():
        raw = path.read_bytes()
        assert len(raw) == octets
        assert _sha256(raw) == digest
    target = _load(TARGET)
    assert [
        row["case_position"] for row in target["ordered_pilot_case_records"]
    ] == list(PILOT_CASES)
    assert target["ordered_pilot_case_records"][4]["logical_count_plan_id"] == (
        "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
    )


def test_parent_pilot_runner_exists() -> None:
    assert RUNNER.is_file() and not RUNNER.is_symlink(), (
        "A4_P6_R_PARENT_PILOT_RUNNER_MISSING"
    )


def _runner_or_skip() -> bytes:
    if not RUNNER.is_file():
        pytest.skip("A4-P6-R fail-first: runner is intentionally absent")
    return RUNNER.read_bytes()


def test_runner_source_is_role_separated_and_process_bounded() -> None:
    raw = _runner_or_skip()
    source = raw.decode("utf-8", errors="strict")
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
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            strings.add(node.value)
    boundary = _load(BOUNDARY)
    allowed = set(
        boundary["independence_contract"]["allowed_standard_library_import_roots"]
    )
    forbidden = set(boundary["independence_contract"]["forbidden_import_roots"])
    assert imports <= allowed
    assert imports.isdisjoint(forbidden)
    assert calls.isdisjoint(
        {"__import__", "compile", "eval", "exec", "system", "popen"}
    )
    assert {"fork", "execve", "wait4", "setrlimit"} <= calls
    assert RUNNER_MARKER in strings
    assert PRODUCER_MARKER not in source and VERIFIER_MARKER not in source
    for required in (
        PRODUCER.relative_to(ROOT).as_posix(),
        VERIFIER.relative_to(ROOT).as_posix(),
        PACKED_BOUNDARY.relative_to(ROOT).as_posix(),
        "--case-position",
        "--candidate-root",
        "--write-output-root",
        "--check-output-root",
    ):
        assert required in source or required in strings
    report = _load(PRODUCER_REPORT)
    for row in report["ordered_case_acceptance_records"]:
        for name in (
            "constructive_candidate_id",
            "verification_receipt_id",
            "result_artifact_id",
        ):
            assert row[name] not in source


def test_runner_writes_checks_and_repeats_exact_pilot(tmp_path: Path) -> None:
    _runner_or_skip()
    first = tmp_path / "first"
    second = tmp_path / "second"
    _assert_success(_run("write", first))
    first_manifest = _validate_output(first)
    first_snapshot = _snapshot(first)
    _assert_success(_run("check", first))
    assert _snapshot(first) == first_snapshot
    _assert_success(_run("write", second))
    assert _validate_output(second) == first_manifest
    assert _snapshot(second) == first_snapshot


def test_runner_public_fail_closed_modes_do_not_repair_or_replace(
    tmp_path: Path,
) -> None:
    _runner_or_skip()
    invalid = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(RUNNER), "--invalid"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=30,
    )
    _assert_reject(invalid)
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o700)
    marker = existing / "user-owned"
    marker.write_bytes(b"preserve")
    before = _snapshot(existing)
    _assert_reject(_run("write", existing))
    _assert_reject(_run("check", existing))
    assert _snapshot(existing) == before
    missing = tmp_path / "missing"
    _assert_reject(_run("check", missing))
    assert not missing.exists()


def test_runner_internal_failure_rolls_back_complete_private_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _runner_or_skip()
    module = _load_runner()
    output = tmp_path / "pilot"

    def injected_failure(*arguments: Any, **keywords: Any) -> Any:
        del keywords
        case_root = arguments[3]
        case_root.mkdir(mode=0o700)
        (case_root / "partial").write_bytes(b"not accepted")
        raise module.RunnerReject("INJECTED_CHILD_FAILURE")

    monkeypatch.setattr(module, "_execute_case", injected_failure)
    with pytest.raises(module.RunnerReject, match="INJECTED_CHILD_FAILURE"):
        module._write_pilot(ROOT, PACKED_BOUNDARY, output)
    assert not output.exists()
    assert not [
        path for path in tmp_path.iterdir() if path.name.startswith(".pilot.private.")
    ]


def test_no_parent_runner_private_leftovers() -> None:
    assert not [
        path
        for path in ROOT.rglob("*")
        if ".raw-v8-v2-pilot-private-" in path.name
        or path.name.startswith(".raw-v8-v2-pilot-")
    ]
