"""Acceptance tests for the parent-owned S1-A2 preflight comparator."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPARATOR_PATH = (
    ROOT / "scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py"
)
CONTRACT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)


def _load_comparator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "raw_v8_preflight_comparator", COMPARATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


@pytest.fixture(scope="session")
def comparator_module() -> ModuleType:
    return _load_comparator()


@pytest.fixture(scope="session")
def executed_comparison(
    tmp_path_factory: pytest.TempPathFactory,
    comparator_module: ModuleType,
) -> dict[str, Any]:
    contract, _contract_raw = comparator_module._load_contract(str(CONTRACT_PATH))
    seed, seed_raw, sources = comparator_module._load_authorities(contract)
    staging = tmp_path_factory.mktemp("raw-v8-preflight-comparator") / "staging"
    staging.mkdir(mode=0o700)
    comparison, reports = comparator_module._run_comparison(
        contract,
        seed,
        seed_raw,
        sources,
        staging,
    )
    return {
        "comparison": comparison,
        "contract": contract,
        "reports": reports,
        "seed": seed,
        "seed_raw": seed_raw,
        "sources": sources,
        "staging": staging,
    }


def test_comparator_source_is_closed_and_uses_only_frozen_imports() -> None:
    contract = json.loads(CONTRACT_PATH.read_bytes())
    separation = contract["implementation_separation_policy"]
    assert COMPARATOR_PATH.is_file()
    source = COMPARATOR_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert roots <= set(separation["allowed_comparator_standard_library_import_roots"])
    assert roots.isdisjoint(separation["forbidden_import_roots"])
    assert calls.isdisjoint(separation["forbidden_ast_call_names"])
    assert "subprocess" not in roots


def test_comparator_executes_both_children_and_proves_exact_agreement(
    executed_comparison: dict[str, Any],
) -> None:
    comparison = executed_comparison["comparison"]
    contract = executed_comparison["contract"]
    expected_members = contract["report_contract"]["comparison_payload_schema"][
        "ordered_member_names"
    ]
    assert list(comparison) == expected_members
    assert comparison["semantic_payload_bytes_equal"] is True
    assert comparison["all_475_case_records_equal"] is True
    assert comparison["all_18_metric_summaries_equal"] is True
    assert comparison["all_resource_limits_satisfied"] is True
    assert comparison["comparison_status"] == "EXACT_AGREEMENT"
    assert comparison["implementation_a_semantic_payload_id"] == (
        "d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b"
    )
    assert (
        comparison["implementation_b_semantic_payload_id"]
        == (comparison["implementation_a_semantic_payload_id"])
    )
    assert comparison["semantic_count_vector_sha256"] == (
        "a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8"
    )


def test_execution_envelopes_are_closed_parent_owned_and_within_f0(
    executed_comparison: dict[str, Any],
    comparator_module: ModuleType,
) -> None:
    contract = executed_comparison["contract"]
    reports = executed_comparison["reports"]
    expected_root = contract["report_contract"][
        "wrapped_report_root_ordered_member_names"
    ]
    expected_envelope = contract["report_contract"]["execution_envelope_schema"][
        "ordered_member_names"
    ]
    for label in ("A", "B"):
        report = reports[label]
        assert list(report) == expected_root
        envelope = report["execution_envelope"]
        assert list(envelope) == expected_envelope
        assert envelope["implementation_label"] == label
        assert envelope["exit_code"] == 0
        assert envelope["stdout_octets"] == 0
        assert envelope["stderr_octets"] == 0
        assert envelope["semantic_payload_raw_octets"] == 1_702_217
        assert envelope["semantic_payload_raw_sha256"] == (
            "27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081"
        )
        comparator_module._enforce_execution_envelope(envelope, contract)


def test_comparator_rejects_semantic_mutation_and_result_disagreement(
    executed_comparison: dict[str, Any],
    comparator_module: ModuleType,
) -> None:
    report_a = executed_comparison["reports"]["A"]
    payload = copy.deepcopy(report_a["semantic_payload"])
    payload["ordered_case_result_records"][0]["ordered_resource_measurements"][0][
        "measured_value"
    ] = 0
    mutated_raw = _pretty_bytes(payload)
    with pytest.raises(comparator_module.Reject) as semantic_error:
        comparator_module._validate_semantic_payload(
            mutated_raw,
            executed_comparison["contract"],
            executed_comparison["seed"],
        )
    assert semantic_error.value.code == "COMPARATOR_REPORT_INVALID"

    with pytest.raises(comparator_module.Reject) as mismatch_error:
        comparator_module._comparison_payload(
            executed_comparison["contract"],
            executed_comparison["seed"],
            executed_comparison["sources"],
            report_a,
            executed_comparison["reports"]["B"],
            b"different canonical payload",
            _pretty_bytes(executed_comparison["reports"]["B"]["semantic_payload"]),
        )
    assert mismatch_error.value.code == "COMPARATOR_RESULT_MISMATCH"


def test_comparator_rejects_resource_overrun_and_nonseparate_sources(
    executed_comparison: dict[str, Any],
    comparator_module: ModuleType,
) -> None:
    contract = executed_comparison["contract"]
    envelope = copy.deepcopy(executed_comparison["reports"]["A"]["execution_envelope"])
    envelope["observed_peak_rss_octets"] = 2_147_483_649
    with pytest.raises(comparator_module.Reject) as resource_error:
        comparator_module._enforce_execution_envelope(envelope, contract)
    assert resource_error.value.code == "COMPARATOR_RESOURCE_EVIDENCE_INVALID"

    same = executed_comparison["sources"]["A"]
    with pytest.raises(comparator_module.Reject) as separation_error:
        comparator_module._validate_source_separation({"A": same, "B": same}, contract)
    assert separation_error.value.code == "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE"

    drifted = copy.copy(executed_comparison["sources"]["A"])
    drifted["raw_sha256"] = "0" * 64
    with pytest.raises(comparator_module.Reject) as drift_error:
        comparator_module._verify_source_unchanged(drifted, contract)
    assert drift_error.value.code == "COMPARATOR_IMPLEMENTATION_NOT_SEPARATE"


def test_comparator_atomic_publication_refuses_overwrite(
    tmp_path: Path,
    comparator_module: ModuleType,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "comparison.json"
    raw = b'{\n  "status": "first"\n}\n'
    comparator_module._publish_atomic(target, raw)
    assert target.read_bytes() == raw
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(comparator_module.Reject) as error:
        comparator_module._publish_atomic(target, b"replacement\n")
    assert error.value.code == "OUTPUT_ATOMICITY_INVALID"
    assert target.read_bytes() == raw


def test_comparator_invalid_cli_is_bounded_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(COMPARATOR_PATH), "--bad"],
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
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr.startswith(
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_COMPARATOR_INVOCATION_INVALID: "
    )
    assert completed.stderr.count(b"\n") == 1
    assert not any(tmp_path.iterdir())


def test_comparison_payload_is_canonical_and_identity_sealed(
    executed_comparison: dict[str, Any],
) -> None:
    comparison = executed_comparison["comparison"]
    raw = _pretty_bytes(comparison)
    assert json.loads(raw) == comparison
    payload = {
        name: value
        for name, value in comparison.items()
        if name != "comparison_payload_id"
    }
    canonical = json.dumps(
        {
            "domain": "RiskYieldMMStep2PreflightComparisonV1V4_9F_RawV8",
            "payload": payload,
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert comparison["comparison_payload_id"] == _sha256(canonical)
