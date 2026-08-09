#!/usr/bin/env python3
"""Run the accepted Raw-V8 Step-2 contract harness against the V4 inventory.

The accepted V3 harness remains byte-stable historical evidence.  This thin
successor first requires the independently validated, physically pinned V4
inventory, checks the V4-only authority patch, and then reuses the unchanged
contract assertions against the preserved registry and fixture subtrees.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, Final

V3_HARNESS_RELATIVE_PATH: Final = "tests/_raw_v8_step2_contract_harness_v49f.py"
V3_HARNESS_OCTETS: Final = 129_364
V3_HARNESS_SHA256: Final = (
    "6bbc1038f41bb5d78f921e68216951bbfa6c1cbc31c2fe96dd3172b545b7dcac"
)
V4_VALIDATOR_RELATIVE_PATH: Final = (
    "scripts/tests/validate_raw_v8_step2_inventory_v4_v49f.py"
)
V4_VALIDATOR_OCTETS: Final = 44_131
V4_VALIDATOR_SHA256: Final = (
    "eac22b7828cb65abc85e282ee4b6386e2bcf71b58473282d1610ba109e0b0124"
)
V4_INVENTORY_RELATIVE_PATH: Final = "tests/raw_v8_step2_inventory_v4_v49f.json"
V4_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v4"
V4_INVENTORY_OCTETS: Final = 5_265_855
V4_INVENTORY_RAW_SHA256: Final = (
    "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
)
V4_INVENTORY_ID: Final = (
    "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
)
AMENDMENT_ROLE: Final = "STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION"
AMENDMENT_SHA256: Final = (
    "f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4"
)
NORMATIVE_ROLES: Final = (
    "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
    "STEP2_V2_CONTRACT_FREEZE",
    "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
    AMENDMENT_ROLE,
    "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
)
COMPACT_CONTRACT: Final = {
    "mathematical_acceptance_rule": "SOUND_UPPER_BOUND_PLUS_LEGAL_ATTAINMENT_V1",
    "global_least_attainer_required": False,
    "ordered_component_choice_evidence_required": False,
    "proof_resource_report_is_separate": True,
    "publication_selection_policy": "PINNED_ACCEPTED_ATTAINER_V1",
    "maximum_publication_row_count": 474,
    "verifier_owned_scope_case_count": 475,
}


class V4HarnessFailure(RuntimeError):
    """Raised when the V4 consumer boundary is not exact."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise V4HarnessFailure(message)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V4HarnessFailure(f"V4 inventory contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise V4HarnessFailure(f"V4 inventory contains non-finite value: {value}")


def _read_pinned_executable(
    path: Path,
    *,
    exact_octets: int,
    expected_sha256: str,
    label: str,
) -> tuple[bytes, tuple[int, ...]]:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1
            and before.st_size == exact_octets,
            f"{label} physical shape differs",
        )
        chunks: list[bytes] = []
        total = 0
        while total < exact_octets:
            chunk = os.read(descriptor, min(65_536, exact_octets - total))
            _require(bool(chunk), f"{label} was truncated")
            chunks.append(chunk)
            total += len(chunk)
        _require(not os.read(descriptor, 1), f"{label} exceeds its exact size")
        after = os.fstat(descriptor)
        signature = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        _require(
            signature
            == (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
            f"{label} changed during read",
        )
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    _require(
        hashlib.sha256(raw).hexdigest() == expected_sha256,
        f"{label} SHA-256 differs",
    )
    return raw, signature


def _read_exact_v4(repository_root: Path) -> tuple[bytes, dict[str, Any]]:
    path = repository_root / V4_INVENTORY_RELATIVE_PATH
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1
            and before.st_size == V4_INVENTORY_OCTETS,
            "V4 inventory physical shape differs",
        )
        chunks: list[bytes] = []
        total = 0
        while total < V4_INVENTORY_OCTETS:
            chunk = os.read(descriptor, min(65_536, V4_INVENTORY_OCTETS - total))
            _require(bool(chunk), "V4 inventory was truncated")
            chunks.append(chunk)
            total += len(chunk)
        _require(not os.read(descriptor, 1), "V4 inventory exceeds its exact size")
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "V4 inventory changed during consumer read",
        )
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    _require(
        hashlib.sha256(raw).hexdigest() == V4_INVENTORY_RAW_SHA256,
        "V4 inventory raw SHA-256 differs",
    )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise V4HarnessFailure("V4 inventory is not strict JSON") from exc
    _require(type(value) is dict, "V4 inventory root is not an object")
    _require(value.get("schema_version") == V4_SCHEMA_VERSION, "V4 schema differs")
    _require(value.get("inventory_sha256") == V4_INVENTORY_ID, "V4 ID differs")
    documents = value.get("normative_document_inputs")
    _require(type(documents) is list, "V4 normative inputs are not an array")
    _require(
        tuple(item.get("document_role") for item in documents) == NORMATIVE_ROLES,
        "V4 normative authority order differs",
    )
    _require(
        documents[3].get("raw_sha256") == AMENDMENT_SHA256,
        "V4 compact-correction authority differs",
    )
    invariants = value.get("invariants")
    _require(type(invariants) is dict, "V4 invariants are not an object")
    _require(
        invariants.get("compact_maximum_proof_v2_contract") == COMPACT_CONTRACT,
        "V4 compact-proof contract differs",
    )
    return raw, value


def _run_independent_validator(repository_root: Path) -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(repository_root / V4_VALIDATOR_RELATIVE_PATH),
            "--repository-root",
            str(repository_root),
            "--inventory",
            str(repository_root / V4_INVENTORY_RELATIVE_PATH),
        ),
        cwd=repository_root,
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    _require(result.returncode == 0, f"V4 validator rejected: {result.stderr}")
    _require(result.stderr == "", "V4 validator emitted stderr on success")
    report = json.loads(result.stdout)
    _require(
        report.get("inventory_sha256") == V4_INVENTORY_ID
        and report.get("maximum_publication_row_count") == 474
        and report.get("verifier_owned_scope_case_count") == 475,
        "V4 validator report differs",
    )


def _load_v3_harness(repository_root: Path) -> ModuleType:
    path = repository_root / V3_HARNESS_RELATIVE_PATH
    spec = importlib.util.spec_from_file_location("_raw_v8_step2_v4_consumer", path)
    _require(spec is not None and spec.loader is not None, "cannot load V3 harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module._GOLDEN_RELATIVE_PATH = V4_INVENTORY_RELATIVE_PATH
    module._INVENTORY_SCHEMA_VERSION = V4_SCHEMA_VERSION
    return module


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(arguments)
    repository_root = namespace.repository_root.resolve(strict=True)
    validator_before = _read_pinned_executable(
        repository_root / V4_VALIDATOR_RELATIVE_PATH,
        exact_octets=V4_VALIDATOR_OCTETS,
        expected_sha256=V4_VALIDATOR_SHA256,
        label="independent V4 validator",
    )
    _run_independent_validator(repository_root)
    validator_after = _read_pinned_executable(
        repository_root / V4_VALIDATOR_RELATIVE_PATH,
        exact_octets=V4_VALIDATOR_OCTETS,
        expected_sha256=V4_VALIDATOR_SHA256,
        label="independent V4 validator",
    )
    _require(validator_before == validator_after, "V4 validator changed during use")
    before, _inventory = _read_exact_v4(repository_root)
    harness_before = _read_pinned_executable(
        repository_root / V3_HARNESS_RELATIVE_PATH,
        exact_octets=V3_HARNESS_OCTETS,
        expected_sha256=V3_HARNESS_SHA256,
        label="accepted V3 contract harness",
    )
    harness = _load_v3_harness(repository_root)
    harness._run_contracts(repository_root)
    harness_after = _read_pinned_executable(
        repository_root / V3_HARNESS_RELATIVE_PATH,
        exact_octets=V3_HARNESS_OCTETS,
        expected_sha256=V3_HARNESS_SHA256,
        label="accepted V3 contract harness",
    )
    _require(harness_before == harness_after, "V3 harness changed during V4 use")
    after, _inventory_after = _read_exact_v4(repository_root)
    _require(before == after, "V4 inventory changed during contract consumption")
    print("PASS raw-v8-step2-contracts-v4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
