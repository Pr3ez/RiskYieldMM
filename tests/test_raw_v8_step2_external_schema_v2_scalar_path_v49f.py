from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_VALIDATOR = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_scalar_path_v49f.py"
)
_LEDGER = "scripts/tests/raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json"
_TOPOLOGY = "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
_CORE = "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
_LEDGER_SHA256 = "b0b8783c8783012d5dc966578c82f348c902f6bf0d44583a4a7d5be6a16079aa"
_LEDGER_OCTETS = 394_277
_ERROR_PREFIX = "Raw-V8 Step-2 external-schema V2 scalar/path error: "


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _canonical(value: Any) -> bytes:
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


def _load() -> dict[str, Any]:
    value = json.loads((_root() / _LEDGER).read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _run(
    ledger: Path,
    *,
    topology: Path | None = None,
    core: Path | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    root = _root()
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(root / _VALIDATOR),
            "--ledger",
            str(ledger),
            "--topology",
            str(root / _TOPOLOGY if topology is None else topology),
            "--core",
            str(root / _CORE if core is None else core),
        ),
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


def _assert_reject(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(_ERROR_PREFIX)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _temporary_ledger(tmp_path: Path, value: dict[str, Any]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_bytes(_canonical(value))
    return path


def _catalog_indexes(
    ledger: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
]:
    schemas = {
        item["value_schema_id"]: item for item in ledger["ordered_value_schemas"]
    }
    languages = {
        item["text_language_id"]: item
        for item in ledger["ordered_text_language_descriptors"]
    }
    assignments = {
        (item["source_type_name"], item["member_name"]): item
        for item in ledger["ordered_member_path_assignments"]
    }
    return schemas, languages, assignments


def _schema_for(
    ledger: dict[str, Any],
    type_name: str,
    member_name: str,
) -> dict[str, Any]:
    schemas, _, assignments = _catalog_indexes(ledger)
    return schemas[assignments[(type_name, member_name)]["value_schema_id"]]


def _language_for(
    ledger: dict[str, Any],
    type_name: str,
    member_name: str,
) -> dict[str, Any]:
    schemas, languages, assignments = _catalog_indexes(ledger)
    schema = schemas[assignments[(type_name, member_name)]["value_schema_id"]]
    return languages[schema["text_language_id"]]


def _dfa_for(
    ledger: dict[str, Any],
    type_name: str,
    member_name: str,
) -> dict[str, Any]:
    language = _language_for(ledger, type_name, member_name)
    assert language["language_kind"] == "ASCII_DFA"
    return next(
        item
        for item in ledger["ordered_ascii_dfa_descriptors"]
        if item["ascii_dfa_id"] == language["ascii_dfa_id"]
    )


def test_scalar_path_ledger_is_exact_canonical_partial_authority() -> None:
    raw = (_root() / _LEDGER).read_bytes()
    ledger = _load()
    assert raw == _canonical(ledger)
    assert len(raw) == _LEDGER_OCTETS
    assert hashlib.sha256(raw).hexdigest() == _LEDGER_SHA256
    assert ledger["component_status"] == "SCALAR_PATH_ONLY_NOT_FULL_REGISTRY"
    assert ledger["member_path_assignment_count"] == 421
    assert ledger["value_schema_count"] == 200
    assert ledger["text_language_count"] == 103
    assert ledger["ascii_dfa_count"] == 9
    assert ledger["unicode_identifier_profile_count"] == 3
    assert ledger["value_schema_kind_counts"] == {
        "ARRAY": 37,
        "EXACT_BOOLEAN": 2,
        "OBJECT_REF": 23,
        "SAFE_INTEGER": 29,
        "TEXT": 109,
    }
    assert ledger["language_kind_counts"] == {
        "ASCII_DFA": 9,
        "BUILTIN": 6,
        "ENUM": 44,
        "LITERAL": 41,
        "UNICODE_IDENTIFIER": 3,
    }


def test_validator_reports_exact_frozen_counts_and_ids() -> None:
    result = _run(_root() / _LEDGER)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report == {
        "ascii_dfa_count": 9,
        "component_status": "SCALAR_PATH_ONLY_NOT_FULL_REGISTRY",
        "core_ledger_sha256": (
            "fc2b888559067fddb5178a87bcae3ab4876e5c17fab766da6ce54581eeff34fb"
        ),
        "ledger_octets": _LEDGER_OCTETS,
        "ledger_path": str(_root() / _LEDGER),
        "ledger_sha256": _LEDGER_SHA256,
        "member_path_assignment_count": 421,
        "scalar_path_component_sha256": (
            "662ff38017af18d32a2bf7593d2ce6f0d7366fa82164a1fbe23742b30e86b51f"
        ),
        "text_language_count": 103,
        "topology_ledger_sha256": (
            "17b6355afcc23438efad97967180fb7e6292b7dd3d72d8b91a0320bfb9696778"
        ),
        "unicode_identifier_profile_count": 3,
        "value_schema_count": 200,
    }


def test_generator_reproduces_frozen_bytes(tmp_path: Path) -> None:
    root = _root()
    output = tmp_path / "generated.json"
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(root / _VALIDATOR),
            "--write-expected-ledger",
            str(output),
            "--topology",
            str(root / _TOPOLOGY),
            "--core",
            str(root / _CORE),
        ),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout == result.stderr == ""
    assert output.read_bytes() == (root / _LEDGER).read_bytes()


def test_path_key_set_is_exactly_the_frozen_topology_key_set() -> None:
    ledger = _load()
    topology = json.loads((_root() / _TOPOLOGY).read_text(encoding="utf-8"))
    actual = [
        (
            item["source_type_name"],
            item["member_position"],
            item["member_name"],
            tuple(item["typed_member_path"]),
            item["member_role"],
        )
        for item in ledger["ordered_member_path_assignments"]
    ]
    expected = [
        (
            item["source_type_name"],
            item["member_position"],
            item["member_name"],
            tuple(item["typed_member_path"]),
            item["member_role"],
        )
        for item in topology["path_ledger"]["record_member_paths"]
    ]
    assert actual == expected
    assert len(actual) == len(set(actual)) == 421
    assert all(
        item["value_schema_id"] for item in ledger["ordered_member_path_assignments"]
    )


def test_strongest_unary_regression_assignments_are_frozen() -> None:
    ledger = _load()
    shutdown = "CapacityMeasurementLocalShutdownSpecV2"
    expected_integer_bounds = {
        "maximum_terminal_ingress_parser_units": (1, 4_096),
        "maximum_terminal_ingress_automatic_outputs": (1, 4_096),
        "maximum_websocket_send_attempts": (1, 1_048_832),
        "maximum_tls_control_send_attempts": (1, 256),
        "maximum_peer_shutdown_polls": (2, 2),
    }
    for member_name, bounds in expected_integer_bounds.items():
        schema = _schema_for(ledger, shutdown, member_name)
        assert schema["schema_kind"] == "SAFE_INTEGER"
        assert (schema["integer_minimum"], schema["integer_maximum"]) == bounds
    parser_array = _schema_for(
        ledger,
        "CapacityMeasurementLocalShutdownResultEvidenceV2",
        "ordered_terminal_parser_transition_event_ids",
    )
    assert (
        parser_array["array_minimum_items"],
        parser_array["array_maximum_items"],
    ) == (0, 4_096)
    close_reason = _language_for(
        ledger,
        shutdown,
        "expected_local_close_reason_sha256",
    )
    assert close_reason["language_kind"] == "LITERAL"
    assert close_reason["ordered_literals"] == [hashlib.sha256(b"").hexdigest()]


def test_exact_root_cardinalities_and_subset_languages_are_frozen() -> None:
    ledger = _load()
    arrays = {
        ("MarkerContractV1", "ordered_marker_kinds"): (19, 19),
        ("MarkerContractV1", "ordered_full_checkpoint_marker_kinds"): (13, 13),
        ("MarkerContractV1", "ordered_checkpoint_operation_records"): (13, 13),
        ("MarkerContractV1", "forbidden_full_checkpoint_marker_kinds"): (5, 5),
        ("TargetFieldRegistryV1", "ordered_vocabulary_definitions"): (25, 25),
        ("TargetFieldRegistryV1", "ordered_value_shape_definitions"): (6, 6),
        ("TargetFieldRegistryV1", "ordered_value_constraint_definitions"): (17, 17),
        ("TargetFieldRegistryV1", "ordered_cross_field_constraint_definitions"): (
            1,
            1,
        ),
        ("TargetFieldRegistryV1", "descriptors"): (185, 185),
        ("OperationCounterSnapshotSchemaV1", "ordered_counter_field_ids"): (66, 66),
        ("OperationCounterSnapshotSchemaV1", "monotone_counter_field_ids"): (57, 57),
        ("OperationCounterSnapshotV1", "values"): (66, 66),
    }
    for key, bounds in arrays.items():
        schema = _schema_for(ledger, *key)
        assert (schema["array_minimum_items"], schema["array_maximum_items"]) == bounds

    context = "TargetObservationContextV2"
    assert (
        len(
            _language_for(ledger, context, "checkpoint_marker_kind")["ordered_literals"]
        )
        == 13
    )
    assert (
        len(
            _language_for(ledger, context, "checkpoint_binding_unavailable_reason")[
                "ordered_literals"
            ]
        )
        == 4
    )
    assert (
        len(
            _language_for(ledger, "TargetObservationClockSpanV2", "unavailable_reason")[
                "ordered_literals"
            ]
        )
        == 5
    )
    assert (
        len(
            _language_for(ledger, "SourceErrorDetailV1", "observation_method")[
                "ordered_literals"
            ]
        )
        == 31
    )
    assert (
        len(
            _language_for(ledger, "SourceErrorDetailV1", "source_failure_phase")[
                "ordered_literals"
            ]
        )
        == 3
    )
    assert (
        len(
            _language_for(
                ledger,
                "CheckpointSelectorEntryV1",
                "checkpoint_marker_kind",
            )["ordered_literals"]
        )
        == 19
    )


def _dfa_accepts(descriptor: dict[str, Any], value: str) -> bool:
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    if not descriptor["minimum_octets"] <= len(raw) <= descriptor["maximum_octets"]:
        return False
    state = descriptor["start_state"]
    for byte in raw:
        matches = [
            row
            for row in descriptor["ordered_transition_rows"]
            if row["source_state"] == state
            and row["inclusive_byte_minimum"] <= byte <= row["inclusive_byte_maximum"]
        ]
        if len(matches) != 1:
            return False
        state = matches[0]["target_state"]
    return state in descriptor["ordered_accepting_states"]


def test_dfa_rows_are_canonical_and_request_id_accepts_hyphen() -> None:
    ledger = _load()
    for descriptor in ledger["ordered_ascii_dfa_descriptors"]:
        rows = descriptor["ordered_transition_rows"]
        keys = [
            (
                row["source_state"],
                row["inclusive_byte_minimum"],
                row["inclusive_byte_maximum"],
                row["target_state"],
            )
            for row in rows
        ]
        assert keys == sorted(keys)
    request = _dfa_for(
        ledger,
        "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
        "generated_request_id",
    )
    assert _dfa_accepts(request, "-")
    assert _dfa_accepts(request, "a-b_C9")
    assert not _dfa_accepts(request, ".")
    assert not _dfa_accepts(request, "x" * 37)


def test_sorted_text_languages_are_orderable_but_time_and_decimal_are_not() -> None:
    ledger = _load()
    for type_name, member_name in (
        ("SourceErrorDetailV1", "field_id"),
        ("CapacityMeasurementVocabularyDefinitionV1", "vocabulary_id"),
    ):
        assert _language_for(ledger, type_name, member_name)["ordering_semantics"] == (
            "UNICODE_SCALAR_LEXICOGRAPHIC"
        )
    builtins = {
        item["built_in_language_kind"]: item
        for item in ledger["ordered_text_language_descriptors"]
        if item["language_kind"] == "BUILTIN"
        and item["built_in_language_kind"] != "CANONICAL_BASE64"
    }
    assert builtins["RAW_CANONICAL_JSON_STRING"]["ordering_semantics"] == (
        "UNICODE_SCALAR_LEXICOGRAPHIC"
    )
    assert builtins["RFC3339_UTC"]["ordering_semantics"] == "NONE"
    assert builtins["UINT128_DECIMAL"]["ordering_semantics"] == "NONE"


def test_dfa_samples_differentially_match_production_regexes() -> None:
    from riskyieldmm.trading import (
        physical_transport_capacity_contracts_v49f_v8 as production,
    )

    ledger = _load()
    cases = {
        "IDEMPOTENCY_KEY": (
            production._IDEMPOTENCY_KEY_RE,  # noqa: SLF001
            _dfa_for(
                ledger,
                "CapacityMeasurementSubscriptionDispatchSpecV2",
                "idempotency_key",
            ),
            ["a", "A-._:9", "", "-bad", "a space", "a" * 129],
        ),
        "REQUEST_ID": (
            production._REQUEST_ID_RE,  # noqa: SLF001
            _dfa_for(
                ledger,
                "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
                "generated_request_id",
            ),
            ["a", "-", "A_9-z", "", ".", "a" * 37],
        ),
        "ERRNO_NAME": (
            production._ERRNO_NAME_RE,  # noqa: SLF001
            _dfa_for(ledger, "SourceErrorDetailV1", "source_errno_name"),
            ["E", "E_AGAIN2", "", "_E", "eagain", "E" * 65],
        ),
        "EXCEPTION_CLASS": (
            production._SAFE_EXCEPTION_CLASS_RE,  # noqa: SLF001
            _dfa_for(ledger, "SourceErrorDetailV1", "source_error_class"),
            ["E", "pkg.Error_2", "", ".Error", "pkg..Error", "pkg.Error-2"],
        ),
        "FIELD_ID": (
            production._FIELD_ID_RE,  # noqa: SLF001
            _dfa_for(ledger, "SourceErrorDetailV1", "field_id"),
            ["a.b", "actor.event_count", "", "A.b", "a.", "a.b.c"],
        ),
    }
    for name, (pattern, descriptor, values) in cases.items():
        for value in values:
            expected = (
                len(value.encode("ascii", errors="ignore"))
                <= descriptor["maximum_octets"]
                and re.fullmatch(pattern, value) is not None
            )
            assert _dfa_accepts(descriptor, value) is expected, (name, value)


@pytest.mark.parametrize(
    "case",
    [
        "missing_path",
        "unknown_schema",
        "schema_semantic_id",
        "language_enum_order",
        "language_semantic_id",
        "dfa_row_order",
        "dfa_overlap",
        "wrong_status",
        "boolean_count",
        "unreachable_schema",
        "unicode_profile_reference",
    ],
)
def test_semantic_mutations_fail_closed(tmp_path: Path, case: str) -> None:
    ledger = copy.deepcopy(_load())
    if case == "missing_path":
        ledger["ordered_member_path_assignments"].pop()
        ledger["member_path_assignment_count"] -= 1
    elif case == "unknown_schema":
        ledger["ordered_member_path_assignments"][0]["value_schema_id"] = "0" * 64
    elif case == "schema_semantic_id":
        ledger["ordered_value_schemas"][0]["nullable"] = not ledger[
            "ordered_value_schemas"
        ][0]["nullable"]
    elif case == "language_enum_order":
        language = next(
            item
            for item in ledger["ordered_text_language_descriptors"]
            if item["language_kind"] == "ENUM"
        )
        language["ordered_literals"][0:2] = reversed(language["ordered_literals"][0:2])
    elif case == "language_semantic_id":
        ledger["ordered_text_language_descriptors"][0]["ordering_semantics"] = (
            "UNICODE_SCALAR_LEXICOGRAPHIC"
        )
    elif case == "dfa_row_order":
        ledger["ordered_ascii_dfa_descriptors"][0]["ordered_transition_rows"][0:2] = (
            reversed(
                ledger["ordered_ascii_dfa_descriptors"][0]["ordered_transition_rows"][
                    0:2
                ]
            )
        )
    elif case == "dfa_overlap":
        rows = ledger["ordered_ascii_dfa_descriptors"][0]["ordered_transition_rows"]
        rows.insert(1, copy.deepcopy(rows[0]))
    elif case == "wrong_status":
        ledger["component_status"] = "FULL_REGISTRY"
    elif case == "boolean_count":
        ledger["value_schema_count"] = True
    elif case == "unreachable_schema":
        duplicate = copy.deepcopy(ledger["ordered_value_schemas"][0])
        duplicate["value_schema_id"] = "f" * 64
        ledger["ordered_value_schemas"].append(duplicate)
        ledger["value_schema_count"] += 1
    elif case == "unicode_profile_reference":
        language = next(
            item
            for item in ledger["ordered_text_language_descriptors"]
            if item["language_kind"] == "UNICODE_IDENTIFIER"
        )
        language["unicode_identifier_profile_id"] = "0" * 64
    else:
        raise AssertionError(case)
    _assert_reject(_run(_temporary_ledger(tmp_path, ledger)))


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "invalid_utf8",
        "bom",
        "duplicate_key",
        "float",
        "nonfinite",
        "oversized_integer",
        "surrogate",
        "deep",
        "minified",
        "unterminated",
    ],
)
def test_invalid_json_and_byte_forms_fail_closed(tmp_path: Path, case: str) -> None:
    raw = (_root() / _LEDGER).read_bytes()
    if case == "empty":
        raw = b""
    elif case == "invalid_utf8":
        raw = raw.replace(b"SCALAR_PATH_ONLY", b"SCALAR_PATH_\xffNLY", 1)
    elif case == "bom":
        raw = b"\xef\xbb\xbf" + raw
    elif case == "duplicate_key":
        raw = raw.replace(
            b"{\n",
            b'{\n  "ascii_dfa_count": 9,\n',
            1,
        )
    elif case == "float":
        raw = raw.replace(b'"ascii_dfa_count": 9', b'"ascii_dfa_count": 9.0', 1)
    elif case == "nonfinite":
        raw = raw.replace(b'"ascii_dfa_count": 9', b'"ascii_dfa_count": NaN', 1)
    elif case == "oversized_integer":
        raw = b'{"value":' + (b"1" * 5_000) + b"}\n"
    elif case == "surrogate":
        raw = raw.replace(
            b'"component_status": "SCALAR_PATH_ONLY_NOT_FULL_REGISTRY"',
            b'"component_status": "\\ud800"',
            1,
        )
    elif case == "deep":
        raw = b"[" * 17 + b"0" + b"]" * 17 + b"\n"
    elif case == "minified":
        raw = json.dumps(_load(), sort_keys=True, separators=(",", ":")).encode()
    elif case == "unterminated":
        raw = b'{"x":"unterminated'
    else:
        raise AssertionError(case)
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    _assert_reject(_run(path))


def test_secure_reader_rejects_leaf_symlink_directory_and_fifo(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_bytes((_root() / _LEDGER).read_bytes())
    link = tmp_path / "link.json"
    link.symlink_to(real)
    _assert_reject(_run(link))
    _assert_reject(_run(tmp_path))

    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "ledger.fifo"
        os.mkfifo(fifo)
        _assert_reject(_run(fifo, timeout=5))


def test_validator_is_stdlib_only_and_has_no_production_or_generator_import() -> None:
    path = _root() / _VALIDATOR
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
    assert "generate_raw_v8_step2_inventory" not in source
    assert "getattr(member" not in source
    assert "startswith(member" not in source
