from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_GENERATOR_RELATIVE_PATH = "scripts/tests/generate_raw_v8_step2_inventory_v49f.py"
_VALIDATOR_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_foundation_v49f.py"
)
_LEDGER_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
)
_GOLDEN_RELATIVE_PATH = "tests/raw_v8_step2_inventory_v49f.json"
_FOUNDATION_LEDGER_SHA256 = (
    "fc2b888559067fddb5178a87bcae3ab4876e5c17fab766da6ce54581eeff34fb"
)
_FOUNDATION_LEDGER_OCTET_COUNT = 10_811
_FOUNDATION_LEDGER_MAXIMUM_OCTETS = 65_536
_FOUNDATION_COMPONENT_SHA256 = (
    "e4bc847e15a2aaf278c5261362bc8fa37a78db6757e5b9f2e34da8be2c6f36f3"
)
_V3_GOLDEN_RAW_SHA256 = (
    "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
)
_GENERATOR_ERROR_PREFIX = "Raw-V8 Step-2 inventory error: "
_VALIDATOR_ERROR_PREFIX = "Raw-V8 Step-2 external-schema V2 foundation error: "
_EXPECTED_PROFILE_IDS = {
    "RAW_V8_UNICODE_IDENTIFIER_A_V1": (
        "e5f43e3e2a1de6656cdffe606ffb5051fec753bc4648b492366c35b284e469c6"
    ),
    "RAW_V8_UNICODE_IDENTIFIER_B_V1": (
        "2c06dc4c23500bb43960078213b42a0f8cc1a425624a5f4bb47d251dcc1947dd"
    ),
    "RAW_V8_UNICODE_IDENTIFIER_C_V1": (
        "7f71f7fc792220d4639530a31424d7e6970a840b306d6c9bb91b608d0c523ccc"
    ),
}
_EXPECTED_SOURCE_IDS = {
    "CompositionExclusions.txt": (
        "a361c1d80b8120f7820ec440c664eb83a07b1e2a722995aa69c2016de19086bb"
    ),
    "DerivedNormalizationProps.txt": (
        "07f3797d2a1f141beca7f11a92a8ed0648a69dfa7fd5206a54e03d978989092b"
    ),
    "NormalizationTest.txt": (
        "1cf368200cdbdfbd6f22f71a26f6b5c499a1b36dabb66cc8eb44475f07e5977f"
    ),
    "PropList.txt": (
        "2134508ac64654d77cee3b434729068d746400a826f5b9f7bf51436914cc8832"
    ),
    "ReadMe.txt": ("f14b2aa9bd0a494dba6abada8ac96eb50ebe81a923795cc1fca7317fd0dd0cee"),
    "UnicodeData.txt": (
        "f6287063cb2282e552dc62c48b0f379174b4ffd1dbcbcc627d3591ab33dc869a"
    ),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_pretty_bytes(value: Any) -> bytes:
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


def _load_ledger() -> dict[str, Any]:
    path = _repository_root() / _LEDGER_RELATIVE_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _run_child(
    *arguments: str,
    cwd: Path | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    root = _repository_root()
    return subprocess.run(
        (sys.executable, "-I", "-B", *arguments),
        cwd=root if cwd is None else cwd,
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


def _run_generator(repository_root: Path) -> subprocess.CompletedProcess[str]:
    generator = _repository_root() / _GENERATOR_RELATIVE_PATH
    return _run_child(
        str(generator),
        "--check-external-schema-v2-foundation",
        "--repository-root",
        str(repository_root),
    )


def _run_validator(ledger: Path) -> subprocess.CompletedProcess[str]:
    validator = _repository_root() / _VALIDATOR_RELATIVE_PATH
    return _run_child(str(validator), "--ledger", str(ledger))


def _parse_report(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert type(report) is dict
    return report


def _assert_controlled_rejection(
    result: subprocess.CompletedProcess[str],
    *,
    prefix: str,
) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(prefix)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _write_temporary_ledger(
    temporary_root: Path,
    payload: bytes,
) -> Path:
    path = temporary_root / _LEDGER_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _mutated_ledger(case: str) -> dict[str, Any]:
    ledger = copy.deepcopy(_load_ledger())
    if case == "missing_root_member":
        ledger.pop("component_status")
    elif case == "extra_root_member":
        ledger["unexpected"] = None
    elif case == "component_status_promoted":
        ledger["component_status"] = "EXTERNAL_SCHEMA_REGISTRY_V2"
    elif case == "source_hash_one_bit_mutation":
        digest = ledger["unicode_source_specs"][0]["sha256"]
        ledger["unicode_source_specs"][0]["sha256"] = (
            digest[:-1] + f"{int(digest[-1], 16) ^ 1:x}"
        )
    elif case == "source_byte_count_drift":
        ledger["unicode_source_specs"][0]["byte_count"] += 1
    elif case == "source_byte_count_boolean":
        ledger["unicode_source_specs"][0]["byte_count"] = True
    elif case == "source_url_drift":
        ledger["unicode_source_specs"][0]["official_url"] += "?mirror=1"
    elif case == "source_unicode_version_drift":
        ledger["unicode_source_specs"][0]["unicode_version"] = "15.1.0"
    elif case == "source_order_swap":
        ledger["unicode_source_specs"][0:2] = reversed(
            ledger["unicode_source_specs"][0:2]
        )
    elif case == "profile_maximum_drift":
        ledger["identifier_profile_specs"][1]["maximum_utf8_octets"] = 257
    elif case == "profile_forbidden_range_drift":
        ledger["identifier_profile_specs"][0]["forbidden_code_point_ranges"][0][1] = (
            "U+001E"
        )
    elif case == "profile_normalization_form_drift":
        ledger["identifier_profile_specs"][0]["normalization_form"] = "NFD"
    elif case == "profile_trim_point_missing":
        ledger["identifier_profile_specs"][0]["edge_trim_code_points"].pop()
    elif case == "profile_trim_surrogate":
        ledger["identifier_profile_specs"][0]["edge_trim_code_points"][-1] = "U+D800"
    elif case == "profile_source_order_swap":
        names = ledger["identifier_profile_specs"][2]["unicode_source_names"]
        names[0:2] = reversed(names[0:2])
    elif case == "surface_missing":
        ledger["surface_assignments"].pop()
    elif case == "surface_profile_reassigned":
        ledger["surface_assignments"][9]["profile_id"] = (
            "RAW_V8_UNICODE_IDENTIFIER_B_V1"
        )
    elif case == "surface_nullability_widened":
        ledger["surface_assignments"][6]["nullable"] = True
    elif case == "surface_typed_path_drift":
        ledger["surface_assignments"][0]["typed_member_path"] = ["expected_topic"]
    elif case == "surface_value_location_drift":
        ledger["surface_assignments"][8]["value_location"] = "MEMBER_VALUE"
    elif case == "surface_position_boolean":
        ledger["surface_assignments"][0]["surface_position"] = True
    elif case == "metadata_domain_drift":
        ledger["metadata_shape_declarations"]["unicode_source"][
            "semantic_id_domain"
        ] = "WRONG"
    elif case == "metadata_member_order_drift":
        members = ledger["metadata_shape_declarations"]["identifier_profile"][
            "identity_payload_member_order"
        ]
        members[0:2] = reversed(members[0:2])
    else:
        raise AssertionError(f"unknown mutation case: {case}")
    return ledger


def test_foundation_ledger_is_canonical_and_has_the_exact_frozen_surface() -> None:
    root = _repository_root()
    ledger_path = root / _LEDGER_RELATIVE_PATH
    raw = ledger_path.read_bytes()
    ledger = _load_ledger()

    assert _sha256(raw) == _FOUNDATION_LEDGER_SHA256
    assert len(raw) == _FOUNDATION_LEDGER_OCTET_COUNT
    assert raw == _canonical_pretty_bytes(ledger)
    assert ledger["component_status"] == (
        "FOUNDATION_ONLY_NOT_EXTERNAL_SCHEMA_REGISTRY_V2"
    )
    assert len(ledger["unicode_source_specs"]) == 6
    assert len(ledger["identifier_profile_specs"]) == 3
    assert len(ledger["surface_assignments"]) == 10
    assert [item["source_name"] for item in ledger["unicode_source_specs"]] == sorted(
        item["source_name"] for item in ledger["unicode_source_specs"]
    )
    for profile in ledger["identifier_profile_specs"]:
        code_points = [
            int(item.removeprefix("U+"), 16)
            for item in profile["edge_trim_code_points"]
        ]
        assert len(code_points) == len(set(code_points)) == 29
        assert code_points == sorted(code_points)
        assert profile["unicode_source_names"] == sorted(
            profile["unicode_source_names"]
        )
    assert [item["surface_position"] for item in ledger["surface_assignments"]] == list(
        range(1, 11)
    )
    assert {
        (
            item["type_name"],
            tuple(item["typed_member_path"]),
            item["value_location"],
        )
        for item in ledger["surface_assignments"]
        if item["nullable"]
    } == {
        (
            "CapacityMeasurementOptionalTextValueV1",
            ("value",),
            "MEMBER_VALUE",
        )
    }


def test_generator_and_independent_validator_report_identical_semantic_ids() -> None:
    root = _repository_root()
    generator_report = _parse_report(_run_generator(root))
    validator_report = _parse_report(_run_validator(root / _LEDGER_RELATIVE_PATH))

    assert generator_report == validator_report
    assert (
        generator_report["foundation_component_sha256"] == _FOUNDATION_COMPONENT_SHA256
    )
    assert generator_report["foundation_ledger_sha256"] == _FOUNDATION_LEDGER_SHA256
    assert (
        generator_report["profile_semantic_id_by_profile_id"] == _EXPECTED_PROFILE_IDS
    )
    assert (
        generator_report["unicode_source_record_id_by_source_name"]
        == _EXPECTED_SOURCE_IDS
    )
    assert generator_report["ordered_unicode_identifier_profile_ids"] == sorted(
        _EXPECTED_PROFILE_IDS.values()
    )
    assert generator_report["ordered_unicode_source_record_ids"] == sorted(
        _EXPECTED_SOURCE_IDS.values()
    )
    assert generator_report["surface_assignment_count_by_profile_id"] == {
        "RAW_V8_UNICODE_IDENTIFIER_A_V1": 5,
        "RAW_V8_UNICODE_IDENTIFIER_B_V1": 4,
        "RAW_V8_UNICODE_IDENTIFIER_C_V1": 1,
    }


def test_foundation_executables_are_stdlib_only_and_do_not_inject_paths() -> None:
    root = _repository_root()
    for relative_path in (_GENERATOR_RELATIVE_PATH, _VALIDATOR_RELATIVE_PATH):
        path = root / relative_path
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
        assert "__import__" not in source
        assert "importlib" not in source
        assert "runpy" not in source
        assert "inspect." not in source


@pytest.mark.parametrize("executable", ["generator", "validator"])
def test_foundation_runtime_audit_rejects_any_production_import_or_read(
    executable: str,
) -> None:
    root = _repository_root()
    script = root / (
        _GENERATOR_RELATIVE_PATH
        if executable == "generator"
        else _VALIDATOR_RELATIVE_PATH
    )
    arguments = (
        [
            str(script),
            "--check-external-schema-v2-foundation",
            "--repository-root",
            str(root),
        ]
        if executable == "generator"
        else [
            str(script),
            "--ledger",
            str(root / _LEDGER_RELATIVE_PATH),
        ]
    )
    wrapper = f"""
import os
import runpy
import sys

def audit(event, args):
    if event == "import" and args and str(args[0]).startswith("riskyieldmm"):
        raise AssertionError("production import attempted")
    if event == "open" and args:
        try:
            path = os.path.abspath(os.fspath(args[0]))
        except TypeError:
            return
        if f"{{os.sep}}riskyieldmm{{os.sep}}" in path:
            raise AssertionError("production source read attempted")

sys.addaudithook(audit)
sys.argv = {arguments!r}
runpy.run_path({str(script)!r}, run_name="__main__")
"""
    result = _run_child("-c", wrapper)
    report = _parse_report(result)
    assert report["foundation_component_sha256"] == _FOUNDATION_COMPONENT_SHA256


@pytest.mark.parametrize(
    "case",
    [
        "missing_root_member",
        "extra_root_member",
        "component_status_promoted",
        "source_hash_one_bit_mutation",
        "source_byte_count_drift",
        "source_byte_count_boolean",
        "source_url_drift",
        "source_unicode_version_drift",
        "source_order_swap",
        "profile_maximum_drift",
        "profile_forbidden_range_drift",
        "profile_normalization_form_drift",
        "profile_trim_point_missing",
        "profile_trim_surrogate",
        "profile_source_order_swap",
        "surface_missing",
        "surface_profile_reassigned",
        "surface_nullability_widened",
        "surface_typed_path_drift",
        "surface_value_location_drift",
        "surface_position_boolean",
        "metadata_domain_drift",
        "metadata_member_order_drift",
    ],
)
def test_semantic_mutations_reject_in_validator_and_byte_pinned_generator(
    tmp_path: Path,
    case: str,
) -> None:
    mutated = _mutated_ledger(case)
    ledger_path = _write_temporary_ledger(
        tmp_path,
        _canonical_pretty_bytes(mutated),
    )

    validator_result = _run_validator(ledger_path)
    _assert_controlled_rejection(
        validator_result,
        prefix=_VALIDATOR_ERROR_PREFIX,
    )
    assert "bytes differ from the independently frozen hash" not in (
        validator_result.stderr
    )

    # The generator CLI intentionally treats the frozen ledger SHA and exact
    # byte count as its authority. These checks prove byte-pin fail-closed
    # behavior; semantic mutation diagnostics are independently exercised by
    # the validator above.
    generator_result = _run_generator(tmp_path)
    _assert_controlled_rejection(
        generator_result,
        prefix=_GENERATOR_ERROR_PREFIX,
    )
    assert (
        "foundation ledger octet count differs" in generator_result.stderr
        or "foundation ledger bytes differ" in generator_result.stderr
    )


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "duplicate_key",
        "nested_duplicate_key",
        "float",
        "nonfinite",
        "noncanonical",
        "invalid_utf8",
        "escaped_surrogate",
        "escaped_surrogate_key",
        "deep_nesting",
        "oversized",
        "unterminated_string",
        "unclosed_container",
        "unopened_container",
    ],
)
def test_invalid_json_forms_have_controlled_fail_closed_rejections(
    tmp_path: Path,
    case: str,
) -> None:
    raw = (_repository_root() / _LEDGER_RELATIVE_PATH).read_bytes()
    if case == "empty":
        raw = b""
    elif case == "duplicate_key":
        raw = raw.replace(
            b"{\n",
            (b'{\n  "canonicalization_version": "riskyieldmm_canonical_json_v1",\n'),
            1,
        )
    elif case == "nested_duplicate_key":
        raw = raw.replace(
            b'{\n      "byte_count": 8911,',
            b'{\n      "byte_count": 8911,\n      "byte_count": 8911,',
            1,
        )
    elif case == "float":
        raw = raw.replace(b'"byte_count": 8911', b'"byte_count": 8911.0', 1)
    elif case == "nonfinite":
        raw = raw.replace(b'"byte_count": 8911', b'"byte_count": NaN', 1)
    elif case == "noncanonical":
        raw = raw.rstrip()
    elif case == "invalid_utf8":
        raw = raw.replace(
            b"CompositionExclusions.txt",
            b"Composition\xffExclusions.txt",
            1,
        )
    elif case == "escaped_surrogate":
        raw = raw.replace(
            b'"source_name": "CompositionExclusions.txt"',
            b'"source_name": "\\ud800"',
            1,
        )
    elif case == "escaped_surrogate_key":
        raw = raw.replace(b'"source_name":', b'"\\ud800":', 1)
    elif case == "deep_nesting":
        raw = b"[" * 10_000 + b"0" + b"]" * 10_000 + b"\n"
    elif case == "oversized":
        raw = b" " * (_FOUNDATION_LEDGER_MAXIMUM_OCTETS + 1)
    elif case == "unterminated_string":
        raw = b'{"value":"unterminated'
    elif case == "unclosed_container":
        raw = b'{"value":1'
    elif case == "unopened_container":
        raw = b"}"
    else:
        raise AssertionError(f"unknown invalid JSON case: {case}")
    ledger_path = _write_temporary_ledger(tmp_path, raw)

    validator_result = _run_validator(ledger_path)
    _assert_controlled_rejection(
        validator_result,
        prefix=_VALIDATOR_ERROR_PREFIX,
    )

    generator_result = _run_generator(tmp_path)
    _assert_controlled_rejection(
        generator_result,
        prefix=_GENERATOR_ERROR_PREFIX,
    )


def test_predecode_scanner_ignores_structure_inside_json_strings(
    tmp_path: Path,
) -> None:
    ledger = _load_ledger()
    ledger["unicode_source_specs"][0]["official_url"] = (
        'https://example.invalid/{["not",{"json":"structure"}]}'
    )
    ledger_path = _write_temporary_ledger(
        tmp_path,
        _canonical_pretty_bytes(ledger),
    )

    result = _run_validator(ledger_path)
    _assert_controlled_rejection(result, prefix=_VALIDATOR_ERROR_PREFIX)
    assert "Unicode source specifications differ" in result.stderr
    assert "nesting" not in result.stderr


def test_foundation_validator_rejects_leaf_symlink_without_traceback(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.json"
    target.write_bytes((_repository_root() / _LEDGER_RELATIVE_PATH).read_bytes())
    link = tmp_path / "ledger-link.json"
    link.symlink_to(target)
    _assert_controlled_rejection(
        _run_validator(link),
        prefix=_VALIDATOR_ERROR_PREFIX,
    )


def test_foundation_validator_rejects_directory_without_traceback(
    tmp_path: Path,
) -> None:
    _assert_controlled_rejection(
        _run_validator(tmp_path),
        prefix=_VALIDATOR_ERROR_PREFIX,
    )


def test_foundation_validator_rejects_fifo_without_blocking(
    tmp_path: Path,
) -> None:
    fifo = tmp_path / "ledger.fifo"
    os.mkfifo(fifo)
    _assert_controlled_rejection(
        _run_validator(fifo),
        prefix=_VALIDATOR_ERROR_PREFIX,
    )


def test_foundation_mode_preserves_default_v3_golden_bytes() -> None:
    root = _repository_root()
    golden = root / _GOLDEN_RELATIVE_PATH
    generator = root / _GENERATOR_RELATIVE_PATH
    before = golden.read_bytes()
    assert _sha256(before) == _V3_GOLDEN_RAW_SHA256

    v3_before = _run_child(
        str(generator),
        "--check",
        "--repository-root",
        str(root),
        "--output",
        str(golden),
    )
    foundation_result = _run_generator(root)
    _parse_report(foundation_result)
    v3_after = _run_child(
        str(generator),
        "--check",
        "--repository-root",
        str(root),
        "--output",
        str(golden),
    )
    assert (
        v3_after.returncode,
        v3_after.stdout,
        v3_after.stderr,
    ) == (
        v3_before.returncode,
        v3_before.stdout,
        v3_before.stderr,
    )
    assert golden.read_bytes() == before
    assert _sha256(golden.read_bytes()) == _V3_GOLDEN_RAW_SHA256
