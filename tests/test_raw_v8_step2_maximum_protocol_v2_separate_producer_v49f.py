from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
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
BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
MANIFEST = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)

EXPECTED_CANDIDATE_OCTETS = 1333
EXPECTED_CANDIDATE_SHA256 = (
    "6dfba23c6d18e96eaf826de408f66d4c69980acbd604d3d7c66f29661f74f9f1"
)
EXPECTED_CANDIDATE_ID = (
    "048df6d26b0d60f217864c32a1b420a34b8427a513a120185de43d822e73b120"
)
PRODUCER_ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_"


def _isolated_environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_producer(
    output_root: Path,
    *,
    repository_root: Path = ROOT,
    producer_path: Path = PRODUCER,
    boundary_path: Path | None = None,
    case_position: str = "5",
    extra_arguments: list[str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if boundary_path is None:
        boundary_path = (
            repository_root
            / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
        )
    arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(producer_path),
        "--repository-root",
        str(repository_root),
        "--boundary",
        str(boundary_path),
        "--case-position",
        case_position,
        "--output-root",
        str(output_root),
    ]
    if extra_arguments:
        arguments.extend(extra_arguments)
    return subprocess.run(
        arguments,
        cwd=repository_root,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
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
    )


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate member: {key}")
        result[key] = value
    return result


def _strict_load(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_duplicate_guard,
        parse_float=lambda value: (_ for _ in ()).throw(ValueError(value)),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    assert type(value) is dict
    return value


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
    envelope = {"domain": domain, "payload": payload}
    return hashlib.sha256(_canonical_bytes(envelope)).hexdigest()


def _assert_success(completed: subprocess.CompletedProcess[bytes]) -> None:
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout == completed.stderr == b""


def _assert_rejected(
    completed: subprocess.CompletedProcess[bytes], output_root: Path
) -> None:
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(PRODUCER_ERROR_PREFIX)
    assert completed.stderr.count(b"\n") == 1
    assert not output_root.exists()


def _candidate_raw(output_root: Path) -> bytes:
    assert {path.name for path in output_root.iterdir()} == {
        "candidate.json",
        "context_objects",
    }
    assert not any((output_root / "context_objects").iterdir())
    return (output_root / "candidate.json").read_bytes()


def _assert_no_private_leftovers(parent: Path) -> None:
    assert not [
        path
        for path in parent.iterdir()
        if path.name.startswith(".raw-v8-v2-producer-")
    ]


def _closure_snapshot(root: Path) -> list[tuple[str, int, int, int, bytes]]:
    result: list[tuple[str, int, int, int, bytes]] = []
    for path in sorted([root, *root.rglob("*")]):
        metadata = path.lstat()
        raw = path.read_bytes() if path.is_file() else b""
        result.append(
            (
                str(path.relative_to(root.parent)),
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                raw,
            )
        )
    return result


def _copy_producer_repository(destination: Path) -> tuple[Path, dict[str, Path]]:
    destination.mkdir(mode=0o700)
    seed = _strict_load(SEED.read_bytes())
    relative_paths = [
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json",
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json",
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json",
        "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py",
        *[
            row["repository_relative_path"]
            for row in seed["ordered_authority_binding_records"]
        ],
    ]
    copied: dict[str, Path] = {}
    for relative_path in relative_paths:
        source = ROOT / relative_path
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[relative_path] = target
    return destination, copied


def test_producer_emits_exact_closed_case5_bundle(tmp_path: Path) -> None:
    output_root = tmp_path / "candidate"
    completed = _run_producer(output_root)
    _assert_success(completed)

    raw = _candidate_raw(output_root)
    candidate = _strict_load(raw)
    boundary = _strict_load(BOUNDARY.read_bytes())
    seed = _strict_load(SEED.read_bytes())
    manifest = _strict_load(MANIFEST.read_bytes())
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    case = next(
        row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
        if row["case_position"] == 5
    )
    plan = next(
        row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
        if row["case_position"] == 5
    )

    assert raw == _pretty_bytes(candidate)
    assert len(raw) == EXPECTED_CANDIDATE_OCTETS
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_CANDIDATE_SHA256
    assert set(candidate) == set(schema["ordered_member_names"])
    assert candidate["seed_catalog_id"] == seed["seed_catalog_id"]
    assert candidate["finalization_manifest_id"] == manifest["finalization_manifest_id"]
    assert candidate["case_position"] == 5
    assert candidate["case_kind"] == case["case_kind"]
    assert candidate["case_binding"] == case["case_binding"]
    assert candidate["logical_count_plan_id"] == plan["logical_count_plan_id"]
    assert candidate["candidate_payload"] == {
        "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
        "witness_record": {"kind": "BOOL", "value": False},
        "scope_witness_context": None,
        "ordered_context_object_entries": [],
    }
    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    assert candidate["constructive_candidate_id"] == EXPECTED_CANDIDATE_ID
    assert candidate["constructive_candidate_id"] == _semantic_id(
        schema["identity_domain"], identity_payload
    )

    root_metadata = output_root.lstat()
    context_metadata = (output_root / "context_objects").lstat()
    file_metadata = (output_root / "candidate.json").lstat()
    assert stat.S_ISDIR(root_metadata.st_mode)
    assert stat.S_ISDIR(context_metadata.st_mode)
    assert stat.S_ISREG(file_metadata.st_mode)
    assert stat.S_IMODE(root_metadata.st_mode) == 0o700
    assert stat.S_IMODE(context_metadata.st_mode) == 0o700
    assert stat.S_IMODE(file_metadata.st_mode) == 0o600
    assert file_metadata.st_nlink == 1
    _assert_no_private_leftovers(tmp_path)


def test_producer_is_byte_deterministic_across_independent_runs(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _assert_success(_run_producer(first))
    _assert_success(_run_producer(second))
    assert _candidate_raw(first) == _candidate_raw(second)
    assert (
        _strict_load(_candidate_raw(first))["constructive_candidate_id"]
        == EXPECTED_CANDIDATE_ID
    )
    _assert_no_private_leftovers(tmp_path)


def test_independent_verifier_accepts_producer_bytes_without_mutating_them(
    tmp_path: Path,
) -> None:
    candidate_root = tmp_path / "candidate"
    verified_root = tmp_path / "verified"
    _assert_success(_run_producer(candidate_root))
    before = _closure_snapshot(candidate_root)
    completed = _run_verifier(candidate_root, verified_root)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout == completed.stderr == b""
    assert before == _closure_snapshot(candidate_root)
    assert {path.name for path in verified_root.iterdir()} == {
        "context_objects",
        "maximum_attainer.json",
        "verification_receipt.json",
    }
    result = _strict_load((verified_root / "maximum_attainer.json").read_bytes())
    receipt = _strict_load((verified_root / "verification_receipt.json").read_bytes())
    assert result["canonical_byte_length"] == 29
    assert result["witness_record"] == {"kind": "BOOL", "value": False}
    assert receipt["constructive_candidate_id"] == EXPECTED_CANDIDATE_ID
    assert receipt["result_artifact_id"] == result["maximum_attainer_id"]
    assert receipt["verification_status"] == "P1_P2_P3_ACCEPTED"


@pytest.mark.parametrize("case_position", ["05", "+5", "5 ", "24", "475"])
def test_producer_rejects_noncanonical_or_unsupported_case_positions(
    tmp_path: Path, case_position: str
) -> None:
    output_root = tmp_path / "candidate"
    completed = _run_producer(output_root, case_position=case_position)
    _assert_rejected(completed, output_root)
    assert completed.returncode == 2
    _assert_no_private_leftovers(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda arguments: arguments + ["--extra"],
        lambda arguments: arguments[:-2],
        lambda arguments: ["--boundary", *arguments[1:]],
    ],
    ids=["extra-argument", "missing-output", "wrong-order"],
)
def test_producer_rejects_invalid_fixed_cli(
    tmp_path: Path, mutation: Callable[[list[str]], list[str]]
) -> None:
    output_root = tmp_path / "candidate"
    arguments = [
        "--repository-root",
        str(ROOT),
        "--boundary",
        str(BOUNDARY),
        "--case-position",
        "5",
        "--output-root",
        str(output_root),
    ]
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(PRODUCER), *mutation(arguments)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=_isolated_environment(),
    )
    _assert_rejected(completed, output_root)
    assert completed.returncode == 2


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_producer_never_overwrites_an_existing_output(
    tmp_path: Path, kind: str
) -> None:
    output_root = tmp_path / "candidate"
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"preserve")
    if kind == "directory":
        output_root.mkdir()
        (output_root / "sentinel").write_bytes(b"preserve")
    elif kind == "file":
        output_root.write_bytes(b"preserve")
    else:
        output_root.symlink_to(sentinel)
    before = sentinel.read_bytes()
    completed = _run_producer(output_root)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.startswith(PRODUCER_ERROR_PREFIX)
    assert completed.stderr.count(b"\n") == 1
    assert sentinel.read_bytes() == before
    if kind == "directory":
        assert (output_root / "sentinel").read_bytes() == b"preserve"
    elif kind == "file":
        assert output_root.read_bytes() == b"preserve"
    else:
        assert output_root.is_symlink()
    _assert_no_private_leftovers(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    ["boundary-bytes", "seed-bytes", "authority-bytes", "hardlink", "symlink"],
)
def test_producer_rejects_authority_substitution_and_link_aliases(
    tmp_path: Path, mutation: str
) -> None:
    mirror, copied = _copy_producer_repository(tmp_path / "mirror")
    authority_path = (
        "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
    )
    if mutation == "boundary-bytes":
        target = copied[
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
        ]
    elif mutation == "seed-bytes":
        target = copied[
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
        ]
    else:
        target = copied[authority_path]
    if mutation.endswith("bytes"):
        raw = target.read_bytes()
        target.write_bytes(raw[:-1] + b" ")
    elif mutation == "hardlink":
        os.link(target, tmp_path / "authority-alias")
    else:
        backing = tmp_path / "authority-backing"
        shutil.copyfile(target, backing)
        target.unlink()
        target.symlink_to(backing)

    output_root = tmp_path / "candidate"
    copied_producer = copied[
        "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
    ]
    completed = _run_producer(
        output_root,
        repository_root=mirror,
        producer_path=copied_producer,
    )
    _assert_rejected(completed, output_root)
    _assert_no_private_leftovers(tmp_path)


def test_producer_rejects_hardlinked_own_source(tmp_path: Path) -> None:
    mirror, copied = _copy_producer_repository(tmp_path / "mirror")
    copied_producer = copied[
        "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
    ]
    os.link(copied_producer, tmp_path / "producer-alias")
    output_root = tmp_path / "candidate"
    completed = _run_producer(
        output_root,
        repository_root=mirror,
        producer_path=copied_producer,
    )
    _assert_rejected(completed, output_root)
    _assert_no_private_leftovers(tmp_path)
