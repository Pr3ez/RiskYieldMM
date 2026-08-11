from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

_V3_HARNESS = "tests/_raw_v8_step2_contract_harness_v49f.py"
_V4_HARNESS = "tests/_raw_v8_step2_contract_harness_v4_v49f.py"
_V3_INVENTORY = "tests/raw_v8_step2_inventory_v49f.json"
_V4_INVENTORY = "tests/raw_v8_step2_inventory_v4_v49f.json"
_V4_GENERATOR = "scripts/tests/generate_raw_v8_step2_inventory_v4_v49f.py"
_V4_VALIDATOR = "scripts/tests/validate_raw_v8_step2_inventory_v4_v49f.py"
_V3_RAW_SHA256 = "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
_V4_RAW_SHA256 = "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
_V3_HARNESS_SHA256 = "6bbc1038f41bb5d78f921e68216951bbfa6c1cbc31c2fe96dd3172b545b7dcac"


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(*arguments: str, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    root = _root()
    return subprocess.run(
        (sys.executable, "-I", "-B", *arguments),
        cwd=root,
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_v3_predecessor_bytes_and_contract_consumer_remain_valid() -> None:
    root = _root()
    before = (root / _V3_INVENTORY).read_bytes()
    harness_before = (root / _V3_HARNESS).read_bytes()
    assert hashlib.sha256(before).hexdigest() == _V3_RAW_SHA256
    assert len(harness_before) == 129_364
    assert hashlib.sha256(harness_before).hexdigest() == _V3_HARNESS_SHA256
    result = _run(
        str(root / _V3_HARNESS),
        "--case",
        "contracts",
        "--repository-root",
        str(root),
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    assert result.stdout == "PASS raw-v8-step2-contracts\n"
    after = (root / _V3_INVENTORY).read_bytes()
    harness_after = (root / _V3_HARNESS).read_bytes()
    assert before == after
    assert harness_before == harness_after


def test_v4_generator_and_independent_validator_accept_the_canonical_bytes() -> None:
    root = _root()
    inventory = (root / _V4_INVENTORY).read_bytes()
    assert hashlib.sha256(inventory).hexdigest() == _V4_RAW_SHA256
    generated = _run(
        str(root / _V4_GENERATOR),
        "--check",
        "--repository-root",
        str(root),
    )
    assert generated.returncode == 0, (generated.stdout, generated.stderr)
    assert generated.stderr == ""
    validated = _run(
        str(root / _V4_VALIDATOR),
        "--repository-root",
        str(root),
        "--inventory",
        str(root / _V4_INVENTORY),
    )
    assert validated.returncode == 0, (validated.stdout, validated.stderr)
    assert validated.stderr == ""


def test_v4_inventory_drives_the_unchanged_runtime_contract_matrix() -> None:
    root = _root()
    result = _run(
        str(root / _V4_HARNESS),
        "--repository-root",
        str(root),
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    assert result.stdout == (
        "PASS raw-v8-step2-contracts\nPASS raw-v8-step2-contracts-v4\n"
    )
