from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT_RELATIVE_PATH = "scripts/tests/validate_unicode_15_0_0_normalization_v49f.py"
_LEDGER_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
)
_VENDORED_SOURCE_DIRECTORY = "scripts/tests/unicode_15_0_0"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_validator():
    path = _repository_root() / _SCRIPT_RELATIVE_PATH
    spec = importlib.util.spec_from_file_location("unicode_v49f_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unicode_validator_source_authority_matches_foundation_ledger() -> None:
    validator = _load_validator()
    ledger = json.loads(
        (_repository_root() / _LEDGER_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    expected = tuple(
        (item["source_name"], item["byte_count"], item["sha256"])
        for item in ledger["unicode_source_specs"]
    )
    assert validator.SOURCE_SPECS == expected


def test_vendored_unicode_sources_are_complete_and_conformant() -> None:
    validator = _load_validator()
    report = validator._build_report(_repository_root() / _VENDORED_SOURCE_DIRECTORY)
    assert report == {
        "component_status": "UNICODE_15_0_0_SOURCE_AND_NORMALIZATION_CONFORMANCE",
        "unicode_version": "15.0.0",
        "runtime_unicode_version": "15.0.0",
        "source_count": 6,
        "source_byte_count_by_name": {
            name: octets for name, octets, _ in validator.SOURCE_SPECS
        },
        "source_sha256_by_name": {
            name: sha256 for name, _, sha256 in validator.SOURCE_SPECS
        },
        "normalization_row_count": 19_074,
        "normalization_part_row_counts": {
            "@Part0": 25,
            "@Part1": 17_029,
            "@Part2": 1_844,
            "@Part3": 176,
        },
        "normalization_assertion_count": 381_480,
        "component_sha256": (
            "f431653cb863b6b0c9659b0a0a04787ddddad500d05c4cb98e6d8eec5c6e00af"
        ),
    }


def test_unicode_validator_executes_the_normative_normalization_equations() -> None:
    validator = _load_validator()
    raw = (
        b"# NormalizationTest-15.0.0.txt\n"
        b"@Part0 # Specific cases\n"
        b"1E0A;1E0A;0044 0307;1E0A;0044 0307;\n"
    )
    rows = validator._parse_normalization_rows(raw)
    assert rows[0][0] == 3
    assert rows[0][1] == "@Part0"
    assert validator._validate_normalization_rows(rows) == 20


def test_unicode_validator_rejects_a_normalization_oracle_mutation() -> None:
    validator = _load_validator()
    raw = (
        b"# NormalizationTest-15.0.0.txt\n@Part0\n1E0A;0044;0044 0307;1E0A;0044 0307;\n"
    )
    rows = validator._parse_normalization_rows(raw)
    with pytest.raises(
        validator.UnicodeConformanceError,
        match="NFC conformance differs",
    ):
        validator._validate_normalization_rows(rows)


@pytest.mark.parametrize(
    "raw,error",
    [
        (
            b"# NormalizationTest-15.0.0.txt\n@Part0\nD800;D800;D800;D800;D800;\n",
            "non-scalar",
        ),
        (
            b"# NormalizationTest-15.0.0.txt\n@Part0\n0041;0041;0041;0041;\n",
            "five columns",
        ),
        (
            b"# NormalizationTest-15.0.0.txt\n0041;0041;0041;0041;0041;\n",
            "precedes a part",
        ),
    ],
)
def test_unicode_validator_rejects_malformed_normalization_rows(
    raw: bytes,
    error: str,
) -> None:
    validator = _load_validator()
    with pytest.raises(validator.UnicodeConformanceError, match=error):
        validator._parse_normalization_rows(raw)


def test_unicode_validator_is_stdlib_only_and_has_no_production_access() -> None:
    path = _repository_root() / _SCRIPT_RELATIVE_PATH
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, path.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] in sys.stdlib_module_names
                assert not alias.name.startswith("riskyieldmm")
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            assert node.module.split(".", 1)[0] in (
                sys.stdlib_module_names | {"__future__"}
            )
            assert not node.module.startswith("riskyieldmm")
    assert "sys.path" not in source
    assert "riskyieldmm" not in source


def test_unicode_validator_cli_fails_closed_without_sources(tmp_path: Path) -> None:
    script = _repository_root() / _SCRIPT_RELATIVE_PATH
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(script),
            "--source-directory",
            str(tmp_path),
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Unicode 15.0.0 conformance error:")
    assert "Traceback" not in result.stderr


def test_unicode_source_reader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    validator = _load_validator()
    fifo = tmp_path / "source.fifo"
    os.mkfifo(fifo)
    with pytest.raises(
        validator.UnicodeConformanceError,
        match="not a direct regular file",
    ):
        validator._read_exact_regular_file(fifo, expected_bytes=1)
